"""
Cafeteria Meal Ordering System — views.

Pages:
  /cafeteria/kiosk/            — idle → staff login → menu select → menu → QR slip
  /cafeteria/kitchen/<type>/   — kitchen view (halal / non_halal / cafe_bar)
  /cafeteria/api/scan-qr/      — QR scan validation (5 scenarios)
  /cafeteria/api/place-order/  — place an order (deducts credits, generates QR)
  /cafeteria/admin/menu/       — admin menu management
  /cafeteria/admin/menu/add/   — add menu item
  /cafeteria/admin/menu/<id>/edit/  — edit menu item
  /cafeteria/admin/stock/      — daily stock management
  /cafeteria/admin/orders/     — order list / cancel
"""
import base64
import hashlib
import hmac
import io
import json
import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    StaffUser, MenuItem, Order, OrderItem, CreditTransaction,
    QRScanLog, OrderingHours,
)


def is_admin(user):
    return user.is_staff or user.is_superuser


# ─── HMAC QR Signing ─────────────────────────────────────────────────────────

def _qr_secret():
    """The HMAC key for QR signing. Derived from SECRET_KEY if QR_SECRET_KEY not set."""
    return (getattr(settings, 'QR_SECRET_KEY', None) or settings.SECRET_KEY).encode()


def sign_order_qr(order: Order) -> str:
    """
    Generate an HMAC-signed token for an order's QR code.
    Format: <order_id>.<nonce>.<hmac_sig>
    One-time use enforced by Order.qr_used flag.
    """
    nonce = secrets.token_urlsafe(12)
    payload = f'{order.id}.{nonce}'
    sig = hmac.new(_qr_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f'{payload}.{sig}'


def verify_order_qr(token: str):
    """
    Verify an HMAC signature. Returns Order or None.
    Does NOT check if already used — caller must check order.qr_used.
    """
    if not token or token.count('.') != 2:
        return None
    try:
        order_id_str, nonce, sig = token.split('.')
        payload = f'{order_id_str}.{nonce}'
        expected = hmac.new(_qr_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, sig):
            return None
        order = Order.objects.filter(id=int(order_id_str), qr_token=token).first()
        return order
    except (ValueError, Order.DoesNotExist):
        return None


def _generate_qr_image_base64(data: str, box_size: int = 6) -> str:
    """Generate QR code as base64 PNG data URL."""
    import qrcode
    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


# ─── Ordering Hours ──────────────────────────────────────────────────────────

def _is_menu_open(menu_type: str) -> bool:
    """Check if a menu is currently accepting orders based on OrderingHours."""
    # Map specific menu types to the OrderingHours menu_type key.
    hours_key = 'cafe_bar' if menu_type == 'cafe_bar' else 'kitchen'
    now = timezone.localtime().time()
    windows = OrderingHours.objects.filter(menu_type=hours_key, is_active=True)
    for w in windows:
        if w.opens_at <= now <= w.closes_at:
            return True
    # If no hours configured, default to open.
    if not windows.exists():
        return True
    return False


def _get_hours_display():
    """Return hours for display on closed screen."""
    return {
        'kitchen': OrderingHours.objects.filter(menu_type='kitchen', is_active=True),
        'cafe_bar': OrderingHours.objects.filter(menu_type='cafe_bar', is_active=True),
    }


# ─── Kiosk ───────────────────────────────────────────────────────────────────

def kiosk_idle_view(request):
    """Idle screen: Staff or Public entry."""
    # Clear any existing kiosk session data when returning to idle.
    if 'cafeteria_cart' in request.session:
        del request.session['cafeteria_cart']
    return render(request, 'cafeteria/kiosk_idle.html', {
        'idle_timeout': getattr(settings, 'STAFF_IDLE_TIMEOUT_SECONDS', 60),
    })


def kiosk_staff_login_view(request):
    """
    Staff login: Face ID or PIN. Uses existing face_verify_ajax for face scan
    and a new PIN endpoint. After login, redirect to menu selection.
    """
    if request.user.is_authenticated and not request.user.is_anonymous:
        return redirect('cafeteria_menu_select')
    return render(request, 'cafeteria/kiosk_staff_login.html')


@require_POST
def kiosk_pin_login_ajax(request):
    """PIN login (same as queue kiosk but redirects to cafeteria menu)."""
    try:
        data = json.loads(request.body)
        staff_id = (data.get('staff_id') or '').strip()
        pin = (data.get('pin') or '').strip()
        if not staff_id or not pin:
            return JsonResponse({'success': False, 'message': 'Staff ID and PIN required'})
        try:
            user = StaffUser.objects.get(staff_id=staff_id, is_active=True)
        except StaffUser.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid Staff ID or PIN'})
        if not user.kiosk_pin or user.kiosk_pin != pin:
            return JsonResponse({'success': False, 'message': 'Invalid Staff ID or PIN'})
        from django.contrib.auth import login
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({'success': True, 'redirect': '/cafeteria/kiosk/menu-select/'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def kiosk_menu_select_view(request):
    """Menu type selection after staff login."""
    kitchen_open = _is_menu_open('halal')
    cafe_bar_open = _is_menu_open('cafe_bar')

    if not kitchen_open and not cafe_bar_open:
        return render(request, 'cafeteria/kiosk_closed.html', {
            'hours': _get_hours_display(),
        })

    context = {
        'kitchen_open': kitchen_open,
        'cafe_bar_open': cafe_bar_open,
        'kitchen_hours': OrderingHours.objects.filter(menu_type='kitchen', is_active=True),
        'cafe_bar_hours': OrderingHours.objects.filter(menu_type='cafe_bar', is_active=True),
    }
    return render(request, 'cafeteria/kiosk_menu_select.html', context)


@login_required
def kiosk_menu_view(request, menu_type):
    """
    Browse menu items and add to cart.
    menu_type: 'kitchen' (shows halal/non_halal tabs) or 'cafe_bar'.
    """
    if menu_type == 'kitchen':
        halal_items = MenuItem.objects.filter(menu_type='halal', is_available=True).order_by('display_order', 'name')
        non_halal_items = MenuItem.objects.filter(menu_type='non_halal', is_available=True).order_by('display_order', 'name')
        items_by_type = {
            'halal': halal_items,
            'non_halal': non_halal_items,
        }
    elif menu_type == 'cafe_bar':
        items_by_type = {
            'cafe_bar': MenuItem.objects.filter(menu_type='cafe_bar', is_available=True).order_by('display_order', 'name'),
        }
    else:
        raise Http404('Unknown menu type')

    cart = request.session.get('cafeteria_cart', {})
    return render(request, 'cafeteria/kiosk_menu.html', {
        'menu_type': menu_type,
        'items_by_type': items_by_type,
        'cart': cart,
    })


@login_required
@require_POST
def kiosk_place_order_ajax(request):
    """
    Place an order: deduct credits, reduce stock atomically, generate QR.
    Expects JSON: {menu_type, items: [{id, quantity, customizations}], collection_time_minutes}
    """
    try:
        data = json.loads(request.body)
        menu_type = data.get('menu_type')
        items_data = data.get('items', [])
        collection_time_minutes = int(data.get('collection_time_minutes', 0))

        if menu_type not in ('halal', 'non_halal', 'cafe_bar'):
            return JsonResponse({'success': False, 'message': 'Invalid menu type'})
        if not items_data:
            return JsonResponse({'success': False, 'message': 'Cart is empty'})

        user = request.user

        with transaction.atomic():
            # Lock menu items for update to prevent race conditions on stock.
            item_ids = [int(i.get('id')) for i in items_data]
            menu_items = {mi.id: mi for mi in MenuItem.objects.select_for_update().filter(id__in=item_ids)}

            subtotal = Decimal('0')
            order_items_buffer = []

            for raw in items_data:
                mid = int(raw.get('id'))
                qty = int(raw.get('quantity', 1))
                cust = raw.get('customizations', {})
                mi = menu_items.get(mid)
                if not mi:
                    return JsonResponse({'success': False, 'message': f'Item {mid} not found'})
                if not mi.is_available:
                    return JsonResponse({'success': False, 'message': f'{mi.name} is unavailable'})
                if mi.quantity_remaining < qty:
                    return JsonResponse({'success': False, 'message': f'{mi.name}: only {mi.quantity_remaining} left'})

                price = mi.staff_price
                line_total = price * qty
                subtotal += line_total

                # Reserve stock.
                mi.quantity_remaining -= qty
                mi.save(update_fields=['quantity_remaining'])

                order_items_buffer.append({
                    'menu_item': mi,
                    'name': mi.name,
                    'price': price,
                    'qty': qty,
                    'cust': cust,
                    'line_total': line_total,
                })

            # Credit calculation.
            available = user.credit_balance
            credits_applied = min(available, subtotal)
            balance_due = subtotal - credits_applied

            if balance_due > 0:
                # Phase 1: reject if insufficient credits (Stripe/PayNow in Phase 2).
                return JsonResponse({
                    'success': False,
                    'message': f'Insufficient credits. Subtotal: S${subtotal}, credits available: S${available}. Card/PayNow payment coming soon.',
                })

            # Create order.
            order = Order.objects.create(
                order_number=Order.next_number(menu_type, is_public=False),
                customer=user,
                menu_type=menu_type,
                status='confirmed',
                subtotal=subtotal,
                credits_applied=credits_applied,
                balance_due=Decimal('0'),
                payment_method='credits',
                collection_time_minutes=collection_time_minutes,
                confirmed_at=timezone.now(),
            )
            order.qr_token = sign_order_qr(order)
            order.save(update_fields=['qr_token'])

            for b in order_items_buffer:
                OrderItem.objects.create(
                    order=order,
                    menu_item=b['menu_item'],
                    name_snapshot=b['name'],
                    price_snapshot=b['price'],
                    quantity=b['qty'],
                    customizations=b['cust'],
                    subtotal=b['line_total'],
                )

            # Debit credits.
            user.credit_balance = available - credits_applied
            user.save(update_fields=['credit_balance'])
            CreditTransaction.objects.create(
                user=user, type='order', amount=-credits_applied,
                balance_after=user.credit_balance, related_order=order,
                notes=f'Order {order.order_number}',
            )

        # Clear cart from session.
        if 'cafeteria_cart' in request.session:
            del request.session['cafeteria_cart']

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'redirect': f'/cafeteria/kiosk/ticket/{order.id}/',
        })
    except Exception as e:
        import logging
        logging.exception('place_order_ajax error')
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def kiosk_ticket_view(request, order_id):
    """QR collection slip — shown after successful order."""
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    qr_image = _generate_qr_image_base64(order.qr_token, box_size=8)
    return render(request, 'cafeteria/kiosk_ticket.html', {
        'order': order,
        'qr_image': qr_image,
    })


# ─── Kitchen View ────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_admin)
def kitchen_view(request, kitchen_type):
    """
    Kitchen/Cafe Bar order display.
    kitchen_type: 'halal', 'non_halal', or 'cafe_bar'.
    """
    if kitchen_type not in ('halal', 'non_halal', 'cafe_bar'):
        raise Http404()

    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    active_orders = Order.objects.filter(
        menu_type=kitchen_type,
        status__in=['confirmed', 'preparing', 'ready'],
        created_at__gte=today_start,
    ).prefetch_related('items').order_by('created_at')

    return render(request, 'cafeteria/kitchen_view.html', {
        'kitchen_type': kitchen_type,
        'orders': active_orders,
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def kitchen_mark_ready_ajax(request, order_id):
    """Mark an order as ready for collection."""
    order = get_object_or_404(Order, pk=order_id)
    order.status = 'ready'
    order.ready_at = timezone.now()
    order.save(update_fields=['status', 'ready_at'])
    return JsonResponse({'success': True})


@login_required
@user_passes_test(is_admin)
@require_POST
def kitchen_scan_qr_ajax(request):
    """
    Scan QR at counter. Returns one of 5 scenarios:
    valid, wrong_counter, duplicate, invalid, not_ready.
    """
    try:
        data = json.loads(request.body)
        token = (data.get('token') or '').strip()
        scanner_counter = data.get('scanner_counter', '')

        order = verify_order_qr(token)

        # Invalid token (tampered/unknown)
        if not order:
            QRScanLog.objects.create(
                scanner_device=scanner_counter, scanned_by=request.user,
                result='invalid', token_preview=token[:40],
                notes='HMAC verification failed',
            )
            return JsonResponse({
                'success': False,
                'result': 'invalid',
                'message': 'Invalid QR code. Please contact staff.',
            })

        # Already used
        if order.qr_used or order.status == 'collected':
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='duplicate', token_preview=token[:40],
                notes=f'Originally collected at {order.collected_at}',
            )
            return JsonResponse({
                'success': False,
                'result': 'duplicate',
                'order_number': order.order_number,
                'original_collected_at': order.collected_at.strftime('%H:%M:%S') if order.collected_at else '',
                'customer_name': order.customer.display_name if order.customer else order.public_name,
                'message': 'QR already used — duplicate scan',
            })

        # Wrong counter
        if order.menu_type != scanner_counter:
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='wrong_counter', token_preview=token[:40],
                notes=f'Order is for {order.menu_type}, scanned at {scanner_counter}',
            )
            return JsonResponse({
                'success': False,
                'result': 'wrong_counter',
                'order_number': order.order_number,
                'correct_counter': order.get_menu_type_display(),
                'message': f'Wrong counter. This order is for {order.get_menu_type_display()}.',
            })

        # Not ready yet
        if order.status not in ('ready',):
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='not_ready', token_preview=token[:40],
                notes=f'Current status: {order.status}',
            )
            return JsonResponse({
                'success': False,
                'result': 'not_ready',
                'order_number': order.order_number,
                'current_status': order.get_status_display(),
                'message': f'Order not ready yet. Status: {order.get_status_display()}',
            })

        # Valid — return order details for confirmation popup.
        return JsonResponse({
            'success': True,
            'result': 'valid',
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer.display_name if order.customer else order.public_name,
            'items': [
                {'name': i.name_snapshot, 'quantity': i.quantity, 'customizations': i.customizations}
                for i in order.items.all()
            ],
        })
    except Exception as e:
        return JsonResponse({'success': False, 'result': 'invalid', 'message': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def kitchen_mark_collected_ajax(request, order_id):
    """After valid QR scan, mark order as collected."""
    order = get_object_or_404(Order, pk=order_id)
    if order.qr_used or order.status == 'collected':
        return JsonResponse({'success': False, 'message': 'Already collected'})
    order.status = 'collected'
    order.collected_at = timezone.now()
    order.qr_used = True
    order.qr_used_at = timezone.now()
    order.save(update_fields=['status', 'collected_at', 'qr_used', 'qr_used_at'])
    QRScanLog.objects.filter(order=order, result='valid').update(notes='Marked collected')
    return JsonResponse({'success': True, 'order_number': order.order_number})


# ─── Admin ───────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_admin)
def admin_menu_list_view(request):
    """Admin menu management: list all items."""
    items = MenuItem.objects.all().order_by('menu_type', 'display_order', 'name')
    return render(request, 'cafeteria/admin_menu_list.html', {'items': items})


@login_required
@user_passes_test(is_admin)
def admin_menu_add_view(request):
    """Add a new menu item."""
    if request.method == 'POST':
        try:
            item = MenuItem.objects.create(
                menu_type=request.POST.get('menu_type', 'halal'),
                category=request.POST.get('category', ''),
                name=request.POST.get('name', ''),
                description=request.POST.get('description', ''),
                staff_price=Decimal(request.POST.get('staff_price') or '0'),
                public_price=Decimal(request.POST.get('public_price') or '0'),
                daily_quantity=int(request.POST.get('daily_quantity') or 0),
                quantity_remaining=int(request.POST.get('daily_quantity') or 0),
                low_stock_threshold=int(request.POST.get('low_stock_threshold') or 3),
                is_available=request.POST.get('is_available') == 'on',
                display_order=int(request.POST.get('display_order') or 0),
                photo=request.FILES.get('photo'),
            )
            messages.success(request, f'Menu item "{item.name}" added.')
            return redirect('cafeteria_admin_menu_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'cafeteria/admin_menu_form.html', {'item': None})


@login_required
@user_passes_test(is_admin)
def admin_menu_edit_view(request, item_id):
    """Edit an existing menu item."""
    item = get_object_or_404(MenuItem, pk=item_id)
    if request.method == 'POST':
        item.menu_type = request.POST.get('menu_type', item.menu_type)
        item.category = request.POST.get('category', '')
        item.name = request.POST.get('name', '')
        item.description = request.POST.get('description', '')
        item.staff_price = Decimal(request.POST.get('staff_price') or '0')
        item.public_price = Decimal(request.POST.get('public_price') or '0')
        item.daily_quantity = int(request.POST.get('daily_quantity') or 0)
        item.low_stock_threshold = int(request.POST.get('low_stock_threshold') or 3)
        item.is_available = request.POST.get('is_available') == 'on'
        item.display_order = int(request.POST.get('display_order') or 0)
        if request.FILES.get('photo'):
            item.photo = request.FILES['photo']
        item.save()
        messages.success(request, f'Updated "{item.name}".')
        return redirect('cafeteria_admin_menu_list')
    return render(request, 'cafeteria/admin_menu_form.html', {'item': item})


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_menu_toggle_ajax(request, item_id):
    """Toggle is_available for a menu item."""
    item = get_object_or_404(MenuItem, pk=item_id)
    item.is_available = not item.is_available
    item.save(update_fields=['is_available'])
    return JsonResponse({'is_available': item.is_available})


@login_required
@user_passes_test(is_admin)
def admin_stock_view(request):
    """Daily stock management."""
    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('qty_'):
                try:
                    item_id = int(key[4:])
                    qty = int(value or 0)
                    MenuItem.objects.filter(pk=item_id).update(
                        daily_quantity=qty,
                        quantity_remaining=qty,
                    )
                except (ValueError, TypeError):
                    pass
        messages.success(request, 'Daily stock updated.')
        return redirect('cafeteria_admin_stock')

    items = MenuItem.objects.all().order_by('menu_type', 'display_order', 'name')
    return render(request, 'cafeteria/admin_stock.html', {'items': items})


@login_required
@user_passes_test(is_admin)
def admin_orders_view(request):
    """Order management / cancellation."""
    status_filter = request.GET.get('status', '')
    qs = Order.objects.all().select_related('customer').prefetch_related('items')
    if status_filter:
        qs = qs.filter(status=status_filter)
    orders = qs[:100]
    return render(request, 'cafeteria/admin_orders.html', {
        'orders': orders,
        'status_filter': status_filter,
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_cancel_order_ajax(request, order_id):
    """Cancel an order: reinstate credits and stock."""
    order = get_object_or_404(Order, pk=order_id)
    if order.status in ('collected', 'cancelled', 'refunded'):
        return JsonResponse({'success': False, 'message': 'Cannot cancel — already finalised'})

    with transaction.atomic():
        # Reinstate stock.
        for item in order.items.all():
            if item.menu_item:
                item.menu_item.quantity_remaining += item.quantity
                item.menu_item.save(update_fields=['quantity_remaining'])

        # Reinstate credits.
        if order.credits_applied > 0 and order.customer:
            order.customer.credit_balance += order.credits_applied
            order.customer.save(update_fields=['credit_balance'])
            CreditTransaction.objects.create(
                user=order.customer, type='refund', amount=order.credits_applied,
                balance_after=order.customer.credit_balance, related_order=order,
                notes=f'Cancel: Order {order.order_number}',
            )

        order.status = 'cancelled'
        order.cancelled_at = timezone.now()
        order.cancel_reason = request.POST.get('reason', 'Admin cancelled')
        order.save(update_fields=['status', 'cancelled_at', 'cancel_reason'])

    return JsonResponse({'success': True, 'message': f'Order {order.order_number} cancelled, credits reinstated.'})


@login_required
@user_passes_test(is_admin)
def admin_qr_logs_view(request):
    """QR scan audit log."""
    logs = QRScanLog.objects.all().select_related('order', 'scanned_by')[:200]
    return render(request, 'cafeteria/admin_qr_logs.html', {'logs': logs})

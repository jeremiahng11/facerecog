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
from django.db.models import Sum, Q, Exists, OuterRef
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    StaffUser, MenuItem, Order, OrderItem, CreditTransaction,
    QRScanLog, OrderingHours, KioskConfig, Holiday,
    EventMenu, EventMenuItem, EventBooking,
)
from .consumers import push_order_event


def _broadcast_order(order, event_type):
    """Push a WebSocket event to relevant groups (kitchen + TV + admin)."""
    payload = {
        'order_id': order.id,
        'order_number': order.order_number,
        'menu_type': order.menu_type,
        'menu_label': order.get_menu_type_display(),
        'status': order.status,
        'customer': order.customer.display_name if order.customer else (order.public_name or 'Public'),
        'is_public': order.is_public,
        'items': [{'name': i.name_snapshot, 'qty': i.quantity} for i in order.items.all()],
        'collection_time_minutes': order.collection_time_minutes,
    }
    # Kitchen/Cafe counter group.
    push_order_event(f'kitchen/{order.menu_type}', event_type, payload)
    # TV displays.
    if order.menu_type == 'cafe_bar':
        push_order_event('tv-cafe-bar', event_type, payload)
    else:
        push_order_event('tv-kitchen', event_type, payload)
    # Admin alerts.
    push_order_event('admin', event_type, payload)


def is_admin(user):
    """Admin privilege check — is_staff, is_superuser, or role='admin'."""
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'admin')


def visible_staff_qs(viewer):
    """Return StaffUser queryset hiding root accounts from non-root viewers."""
    qs = StaffUser.objects.all()
    if not getattr(viewer, 'is_root', False):
        qs = qs.exclude(is_root=True)
    return qs


def is_kitchen_user(user):
    """Can access kitchen counter views (halal, non_halal)."""
    return user.is_authenticated and (is_admin(user) or getattr(user, 'role', '') == 'kitchen')


def is_cafe_bar_user(user):
    """Can access cafe bar counter."""
    return user.is_authenticated and (is_admin(user) or getattr(user, 'role', '') == 'cafe_bar')


def is_kitchen_or_cafe_bar_user(user):
    """Can access any counter (kitchen, cafe_bar, or admin)."""
    return user.is_authenticated and (is_admin(user) or getattr(user, 'role', '') in ('kitchen', 'cafe_bar', 'kitchen_admin'))


def is_kitchen_admin(user):
    """True for full admins OR users with role='kitchen_admin' (menu/event-menu editing)."""
    return user.is_authenticated and (is_admin(user) or getattr(user, 'role', '') == 'kitchen_admin')


def _user_can_scan_counter(user, counter: str) -> bool:
    """Is this user allowed to scan at this counter?"""
    if is_admin(user):
        return True
    if counter in ('halal', 'non_halal') and is_kitchen_user(user):
        return True
    if counter == 'cafe_bar' and is_cafe_bar_user(user):
        return True
    return False


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


# ─── Vending Machine Staff QR ────────────────────────────────────────────────

def sign_staff_vending_qr(user) -> str:
    """
    Generate a permanent HMAC-signed token identifying a staff member.
    Format: VEND:<staff_id>.<hmac_sig>
    Unlike order QR codes, this is reusable — the vending machine sends
    this token to our API along with the purchase amount.
    """
    payload = f'VEND:{user.staff_id}'
    sig = hmac.new(_qr_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f'{payload}.{sig}'


def verify_staff_vending_qr(token: str):
    """
    Verify a staff vending QR token.  Returns StaffUser or None.
    Token format: VEND:<staff_id>.<hmac_sig>
    """
    if not token or not token.startswith('VEND:'):
        return None
    try:
        prefix_and_id, sig = token.rsplit('.', 1)
        expected = hmac.new(_qr_secret(), prefix_and_id.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, sig):
            return None
        staff_id = prefix_and_id[5:]  # strip 'VEND:'
        return StaffUser.objects.filter(staff_id=staff_id, is_active=True).first()
    except (ValueError, StaffUser.DoesNotExist):
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
    """
    Check whether a menu is currently accepting orders.

    Rules (applied in order):
      1. If today is a configured Holiday that closes this scope → closed.
      2. Active OrderingHours windows for the given menu_type filtered to
         today's weekday.
      3. If any such window covers the current local time → open.
      4. If no windows exist at all for the menu_type → default open
         (backward-compat with pre-hours deployments).
    """
    hours_key = 'cafe_bar' if menu_type == 'cafe_bar' else 'kitchen'
    today = timezone.localdate()
    now = timezone.localtime().time()

    # 1. Holidays.
    holiday = Holiday.objects.filter(date=today).first()
    if holiday and holiday.closes(hours_key):
        return False

    # 2–3. OrderingHours for this menu + today's weekday.
    weekday = today.weekday()  # Mon=0 … Sun=6
    windows = OrderingHours.objects.filter(menu_type=hours_key, is_active=True)
    if not windows.exists():
        return True  # never configured → open by default
    windows_today = [w for w in windows if w.applies_to_weekday(weekday)]
    if not windows_today:
        return False  # weekend / day off
    for w in windows_today:
        if w.opens_at <= now <= w.closes_at:
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
    cfg = KioskConfig.get()
    return render(request, 'cafeteria/kiosk_idle.html', {
        'idle_timeout': cfg.idle_landing_seconds,
    })


def kiosk_staff_login_view(request):
    """
    Staff login: Face ID or PIN. Uses existing face_verify_ajax for face scan
    and a new PIN endpoint. After login, redirect to menu selection.
    """
    if request.user.is_authenticated and not request.user.is_anonymous:
        return redirect('cafeteria_menu_select')
    return render(request, 'cafeteria/kiosk_staff_login.html', {
        'idle_timeout': KioskConfig.get().idle_session_seconds,
    })


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
        'idle_timeout': KioskConfig.get().idle_session_seconds,
    }
    return render(request, 'cafeteria/kiosk_menu_select.html', context)


@login_required
def kiosk_menu_view(request, menu_type):
    """
    Browse menu items and add to cart.

    `menu_type` in the URL picks the INITIAL tab (kitchen → halal,
    cafe_bar → cafe_bar) but the page renders all three sub-menus
    (Halal / Non-Halal / Cafe Bar) as tabs so the user can freely
    toggle between them inside a single ordering flow.
    """
    if menu_type not in ('kitchen', 'cafe_bar'):
        raise Http404('Unknown menu type')

    items_by_type = {
        'halal':     MenuItem.objects.filter(menu_type='halal',     is_available=True).order_by('display_order', 'name'),
        'non_halal': MenuItem.objects.filter(menu_type='non_halal', is_available=True).order_by('display_order', 'name'),
        'cafe_bar':  MenuItem.objects.filter(menu_type='cafe_bar',  is_available=True).order_by('display_order', 'name'),
    }

    kitchen_open = _is_menu_open('halal')  # both halal + non_halal share 'kitchen' hours
    cafe_bar_open = _is_menu_open('cafe_bar')

    # Initial tab selection based on which card was tapped on menu-select.
    if menu_type == 'cafe_bar':
        initial_tab = 'cafe_bar' if cafe_bar_open else ('halal' if kitchen_open else 'cafe_bar')
    else:
        initial_tab = 'halal' if kitchen_open else 'cafe_bar'

    cart = request.session.get('cafeteria_cart', {})
    return render(request, 'cafeteria/kiosk_menu.html', {
        'menu_type': menu_type,
        'items_by_type': items_by_type,
        'cart': cart,
        'initial_tab': initial_tab,
        'kitchen_open': kitchen_open,
        'cafe_bar_open': cafe_bar_open,
        'idle_timeout': KioskConfig.get().idle_session_seconds,
    })


@login_required
@require_POST
def kiosk_place_order_ajax(request):
    """
    Place a staff order. Supports mixed carts (items from multiple menus).
    Credits auto-applied; if insufficient, pay_method=stripe/paynow can cover
    the balance (returns checkout URL for the balance).
    Expects JSON: {items: [{id, quantity, customizations}], collection_time_minutes, pay_method}
    """
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        collection_time_minutes = int(data.get('collection_time_minutes', 0))
        pay_method = data.get('pay_method', 'credits')  # 'credits', 'stripe', 'paynow'
        source = (data.get('source') or 'kiosk').strip().lower()  # 'kiosk', 'portal', or 'admin'
        source_suffix = f'?source={source}' if source in ('kiosk', 'portal', 'admin') else ''

        if not items_data:
            return JsonResponse({'success': False, 'message': 'Cart is empty'})

        user = request.user

        with transaction.atomic():
            item_ids = [int(i.get('id')) for i in items_data]
            menu_items = {mi.id: mi for mi in MenuItem.objects.select_for_update().filter(id__in=item_ids)}

            subtotal = Decimal('0')
            order_items_buffer = []
            menu_types_in_cart = set()

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
                mi.quantity_remaining -= qty
                mi.save(update_fields=['quantity_remaining'])

                menu_types_in_cart.add(mi.menu_type)
                order_items_buffer.append({
                    'menu_item': mi, 'name': mi.name, 'price': price,
                    'qty': qty, 'cust': cust, 'line_total': line_total,
                    'menu_type': mi.menu_type,
                })

            # Determine order-level menu type and prefix.
            is_mixed = len(menu_types_in_cart) > 1
            order_menu_type = 'mixed' if is_mixed else next(iter(menu_types_in_cart))

            # Credit calculation.
            available = user.credit_balance
            credits_applied = min(available, subtotal)
            balance_due = subtotal - credits_applied

            # Validate payment if balance remains.
            if balance_due > 0 and pay_method == 'credits':
                return JsonResponse({
                    'success': False,
                    'insufficient_credits': True,
                    'balance_due': str(balance_due),
                    'message': f'Insufficient credits. Balance due: S${balance_due}. Choose Stripe or PayNow to pay the balance.',
                })

            # Create order.
            order = Order.objects.create(
                order_number=Order.next_number(order_menu_type, is_public=False, is_mixed=is_mixed),
                customer=user,
                menu_type=order_menu_type,
                is_mixed=is_mixed,
                status='ready' if balance_due == 0 else 'pending',
                subtotal=subtotal,
                credits_applied=credits_applied,
                balance_due=balance_due,
                payment_method='credits' if balance_due == 0 else pay_method,
                collection_time_minutes=collection_time_minutes,
                confirmed_at=timezone.now() if balance_due == 0 else None,
                ready_at=timezone.now() if balance_due == 0 else None,
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
                    menu_type_snapshot=b['menu_type'],
                )

            # Debit credits.
            if credits_applied > 0:
                user.credit_balance = available - credits_applied
                user.save(update_fields=['credit_balance'])
                CreditTransaction.objects.create(
                    user=user, type='order', amount=-credits_applied,
                    balance_after=user.credit_balance, related_order=order,
                    notes=f'Order {order.order_number}',
                )

            # Handle balance-due payment via Stripe/PayNow.
            if balance_due > 0:
                from .payments import create_stripe_checkout_session, build_paynow_qr
                if pay_method == 'stripe':
                    sess = create_stripe_checkout_session(
                        balance_due, user.staff_id, {'order_id': str(order.id)}
                    )
                    if sess:
                        return JsonResponse({
                            'success': True, 'requires_payment': True,
                            'order_id': order.id, 'order_number': order.order_number,
                            'checkout_url': sess['url'],
                        })
                elif pay_method == 'paynow':
                    qr = build_paynow_qr(balance_due, reference=f'Order-{order.order_number}')
                    return JsonResponse({
                        'success': True, 'requires_payment': True,
                        'order_id': order.id, 'order_number': order.order_number,
                        'paynow_qr': qr, 'balance_due': str(balance_due),
                    })

        # Clear cart from session.
        if 'cafeteria_cart' in request.session:
            del request.session['cafeteria_cart']

        # Broadcast to kitchen + TV + admin via WebSocket.
        _broadcast_order(order, 'created')

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'redirect': f'/cafeteria/kiosk/ticket/{order.id}/{source_suffix}',
        })
    except Exception as e:
        import logging
        logging.exception('place_order_ajax error')
        return JsonResponse({'success': False, 'message': str(e)})


def _escpos_qr_raster(data: str, box_size: int = 5) -> bytes:
    """
    Render a QR code for `data` as an ESC/POS raster bitmap (GS v 0).

    MPT-2 and most 58mm BT thermals support GS v 0 even when they don't
    support the native QR tag GS ( k. Returns the complete ESC/POS byte
    sequence ready to be appended to the print stream.
    """
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('1')

    w, h = img.size
    pad = (8 - (w % 8)) % 8
    if pad:
        new = Image.new('1', (w + pad, h), color=1)
        new.paste(img, (0, 0))
        img = new
        w += pad
    bytes_per_row = w // 8

    raster = bytearray()
    for y in range(h):
        for xb in range(bytes_per_row):
            byte = 0
            for bit in range(8):
                x = xb * 8 + bit
                if img.getpixel((x, y)) == 0:
                    byte |= 1 << (7 - bit)
            raster.append(byte)

    header = bytearray(b'\x1d\x76\x30\x00')  # GS v 0, mode 0
    header.append(bytes_per_row & 0xff)
    header.append((bytes_per_row >> 8) & 0xff)
    header.append(h & 0xff)
    header.append((h >> 8) & 0xff)
    return bytes(header) + bytes(raster)


def _escpos_receipt_b64(order) -> str:
    """
    MPT-2-compatible ESC/POS thermal receipt encoded as base64 — handed
    to RawBT via the rawbt:<base64> URL scheme for true silent printing
    (no browser dialog). Requires: MPT-2 in ESC/POS mode + RawBT app
    installed + printer paired.
    """
    ESC = b'\x1b'
    INIT = ESC + b'@'
    CENTER = ESC + b'a\x01'
    LEFT = ESC + b'a\x00'
    DBL = ESC + b'!\x30'
    NORMAL = ESC + b'!\x00'

    def line(s):
        return s.encode('ascii', 'ignore') + b'\n'

    buf = bytearray()
    buf += INIT
    buf += CENTER
    buf += DBL + line('CAFETERIA') + NORMAL
    buf += line('=' * 32)

    name = ''
    if order.customer_id:
        name = getattr(order.customer, 'display_name', '') or getattr(order.customer, 'full_name', '') or ''
    if not name:
        name = getattr(order, 'public_name', '') or 'Guest'
    buf += line(name[:32])
    buf += b'\n'

    buf += line('ORDER NUMBER')
    buf += DBL + line(order.order_number) + NORMAL
    buf += b'\n'

    if order.qr_token:
        buf += _escpos_qr_raster(order.qr_token, box_size=5)
        buf += b'\n'

    buf += LEFT
    buf += line('-' * 32)
    for it in order.items.all():
        buf += line(f'{it.quantity}x {it.name_snapshot}'[:32])
    buf += line('-' * 32)
    buf += line(f'Total    S${order.subtotal:.2f}')
    if order.credits_applied and order.credits_applied > 0:
        buf += line(f'Credits -S${order.credits_applied:.2f}')
    buf += b'\n'

    buf += CENTER
    buf += line(order.created_at.strftime('%d %b %Y  %H:%M'))
    buf += line('Thank you!')
    buf += b'\n'  # just enough feed to clear the tear bar

    return base64.b64encode(bytes(buf)).decode('ascii')


@login_required
def kiosk_ticket_print_view(request, order_id):
    """
    Dedicated 58mm-wide print-only page for an order — mirrors the
    queue_print pattern from the sister branch. Opened in a new tab
    from the main ticket page. Page-local 'Print Ticket' button calls
    window.print() (silent under Fully Kiosk; dialog otherwise).
    """
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    qr_image = _generate_qr_image_base64(order.qr_token, box_size=5)
    name = ''
    if order.customer_id:
        name = getattr(order.customer, 'display_name', '') or getattr(order.customer, 'full_name', '') or ''
    if not name:
        name = getattr(order, 'public_name', '') or 'Guest'
    return render(request, 'cafeteria/ticket_print.html', {
        'order': order,
        'qr_image': qr_image,
        'name': name,
    })


def public_ticket_print_view(request, order_id):
    """
    Public walk-in print-only page — no login required (matches the public
    ticket). 58mm layout identical to kiosk_ticket_print.
    """
    order = get_object_or_404(Order, pk=order_id, is_public=True)
    qr_image = _generate_qr_image_base64(order.qr_token, box_size=5)
    name = getattr(order, 'public_name', '') or 'Walk-in'
    return render(request, 'cafeteria/ticket_print.html', {
        'order': order,
        'qr_image': qr_image,
        'name': name,
    })


@login_required
def kiosk_ticket_view(request, order_id):
    """QR collection slip — shown after successful order.

    Determines where the 'Done' button sends the user based on order source
    (kiosk vs. staff portal) and the user's role.
    """
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    qr_image = _generate_qr_image_base64(order.qr_token, box_size=8)

    source = (request.GET.get('source') or '').strip().lower()
    if source == 'admin':
        done_url = '/cafeteria/admin/my-orders/'
        done_label = 'Back to My Orders'
    elif source == 'portal':
        done_url = '/cafeteria/portal/'
        done_label = 'Back to Home'
    else:
        done_url = '/cafeteria/kiosk/'
        done_label = 'Done'

    return render(request, 'cafeteria/kiosk_ticket.html', {
        'order': order,
        'qr_image': qr_image,
        'done_url': done_url,
        'done_label': done_label,
        'idle_timeout': KioskConfig.get().idle_session_seconds,
        'post_print_timeout': KioskConfig.get().post_print_seconds,
        'escpos_b64': _escpos_receipt_b64(order),
    })


# ─── Kitchen View ────────────────────────────────────────────────────────────

@login_required
def kitchen_view(request, kitchen_type):
    """
    Kitchen/Cafe Bar order display. Shows only items belonging to this
    counter (for mixed orders, filters the item list per counter).
    Access: admin + kitchen users for halal/non_halal, admin + cafe_bar users for cafe_bar.
    """
    if kitchen_type not in ('halal', 'non_halal', 'cafe_bar'):
        raise Http404()
    if not _user_can_scan_counter(request.user, kitchen_type):
        return render(request, 'cafeteria/access_denied.html', {
            'required_role': 'Kitchen Counter' if kitchen_type in ('halal', 'non_halal') else 'Cafe Bar Counter',
        }, status=403)

    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    # Only show orders that still have UNCOLLECTED items for this counter.
    # Mixed orders drop off a counter once its items are collected, even if
    # other counters still have items pending.
    uncollected_here = OrderItem.objects.filter(
        order=OuterRef('pk'),
        collected_at__isnull=True,
    ).filter(
        Q(menu_type_snapshot=kitchen_type)
        | Q(menu_type_snapshot='', menu_item__menu_type=kitchen_type)
    )
    active_orders = Order.objects.filter(
        status__in=['confirmed', 'preparing', 'ready'],
        created_at__gte=today_start,
    ).annotate(
        _has_uncollected_here=Exists(uncollected_here),
    ).filter(
        _has_uncollected_here=True,
    ).prefetch_related('items', 'items__menu_item').order_by('created_at')

    # For each order, attach the filtered item list for this counter
    # (excluding items already collected at this counter).
    for order in active_orders:
        order.counter_items = [
            i for i in order.items.all()
            if (i.menu_type_snapshot or (i.menu_item.menu_type if i.menu_item else '')) == kitchen_type
               and i.collected_at is None
        ]

    return render(request, 'cafeteria/kitchen_view.html', {
        'kitchen_type': kitchen_type,
        'orders': active_orders,
    })


@login_required
@user_passes_test(is_kitchen_or_cafe_bar_user)
@require_POST
def kitchen_mark_ready_ajax(request, order_id):
    """Mark an order as ready for collection."""
    order = get_object_or_404(Order, pk=order_id)
    order.status = 'ready'
    order.ready_at = timezone.now()
    order.save(update_fields=['status', 'ready_at'])
    _broadcast_order(order, 'ready')
    return JsonResponse({'success': True})


@login_required
@user_passes_test(is_kitchen_or_cafe_bar_user)
@require_POST
def kitchen_scan_qr_ajax(request):
    """
    Scan QR at counter. Detects both:
    - PAYMENT QR (public terminal payment) → cafe bar only, shows pay-up UI
    - COLLECTION QR (normal) → 5 scenarios: valid, wrong_counter, duplicate,
      invalid, not_ready.
    Mixed orders: scan shows only the items belonging to this counter;
    marking collected only marks those items (other counter marks its own).
    """
    try:
        data = json.loads(request.body)
        token = (data.get('token') or '').strip()
        scanner_counter = data.get('scanner_counter', '')

        # ── First check: is it a payment QR? ──────────────────────
        if token.startswith('pay-') or ':' in token and 'pay' in token.split(':')[0]:
            from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
            signer = TimestampSigner(salt='payment-qr')
            try:
                val = signer.unsign(token, max_age=60 * 60 * 24)  # 24h validity
                if not val.startswith('pay-'):
                    raise BadSignature()
                order_id = int(val[4:])
                order = Order.objects.prefetch_related('items').get(pk=order_id)
            except (BadSignature, SignatureExpired, ValueError, Order.DoesNotExist):
                QRScanLog.objects.create(
                    scanner_device=scanner_counter, scanned_by=request.user,
                    result='invalid', token_preview=token[:40],
                    notes='Invalid payment QR',
                )
                return JsonResponse({
                    'result': 'invalid',
                    'message': 'Invalid payment QR code.',
                })

            # Payment QR only usable at cafe bar.
            if scanner_counter != 'cafe_bar':
                return JsonResponse({
                    'result': 'wrong_counter',
                    'order_number': order.order_number,
                    'correct_counter': 'Cafe Bar (for payment)',
                    'message': 'Payment QRs are processed at the Cafe Bar Counter.',
                })

            if order.payment_received_at:
                return JsonResponse({
                    'result': 'duplicate',
                    'order_number': order.order_number,
                    'message': 'Payment already received for this order.',
                    'original_collected_at': order.payment_received_at.strftime('%H:%M:%S'),
                })

            # Payment QR is valid — show payment UI.
            return JsonResponse({
                'result': 'payment_pending',
                'order_id': order.id,
                'order_number': order.order_number,
                'customer_name': order.public_name or 'Walk-in',
                'amount_due': str(order.subtotal),
                'items': [
                    {'name': i.name_snapshot, 'quantity': i.quantity, 'subtotal': str(i.subtotal)}
                    for i in order.items.all()
                ],
            })

        # ── Otherwise it's a collection QR ────────────────────────
        order = verify_order_qr(token)
        if not order:
            QRScanLog.objects.create(
                scanner_device=scanner_counter, scanned_by=request.user,
                result='invalid', token_preview=token[:40],
                notes='HMAC verification failed',
            )
            return JsonResponse({
                'result': 'invalid',
                'message': 'Invalid QR code. Please contact staff.',
            })

        # Which items in this order belong to this counter?
        all_items = list(order.items.all())
        counter_items = [i for i in all_items if (i.menu_type_snapshot or (i.menu_item.menu_type if i.menu_item else '')) == scanner_counter]
        other_items = [i for i in all_items if i not in counter_items]

        # If this counter has no items in the order → wrong counter.
        if not counter_items:
            # Tell the user which counter(s) the order IS for.
            other_types = sorted({(i.menu_type_snapshot or (i.menu_item.menu_type if i.menu_item else 'unknown')) for i in all_items})
            human = ', '.join({
                'halal': 'Local Kitchen', 'non_halal': 'International Kitchen', 'cafe_bar': 'Cafe Bar',
            }.get(t, t) for t in other_types)
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='wrong_counter', token_preview=token[:40],
                notes=f'Scanned at {scanner_counter}, order has items for {human}',
            )
            return JsonResponse({
                'result': 'wrong_counter',
                'order_number': order.order_number,
                'correct_counter': human,
                'message': f'Wrong counter. This order has items for {human}.',
            })

        # Already all collected at this counter?
        if all(i.collected_at for i in counter_items):
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='duplicate', token_preview=token[:40],
                notes=f'All {scanner_counter} items already collected',
            )
            first_collected = min(i.collected_at for i in counter_items)
            return JsonResponse({
                'result': 'duplicate',
                'order_number': order.order_number,
                'original_collected_at': first_collected.strftime('%H:%M:%S'),
                'customer_name': order.customer.display_name if order.customer else order.public_name,
                'message': f'Items at this counter already collected.',
            })

        # Not ready yet?
        # Accept any active (confirmed/preparing/ready) status — orders
        # are ready to collect as soon as they're placed and paid.
        if order.status not in ('confirmed', 'preparing', 'ready'):
            QRScanLog.objects.create(
                order=order, scanner_device=scanner_counter, scanned_by=request.user,
                result='not_ready', token_preview=token[:40],
                notes=f'Current status: {order.status}',
            )
            return JsonResponse({
                'result': 'not_ready',
                'order_number': order.order_number,
                'current_status': order.get_status_display(),
                'message': f'Order not ready yet. Status: {order.get_status_display()}',
            })

        # Scheduled? Orders with collection_time_minutes can still be
        # collected early — no extra check needed; status=ready is enough.

        # Valid — return items for THIS counter only.
        return JsonResponse({
            'result': 'valid',
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer.display_name if order.customer else order.public_name,
            'items': [
                {
                    'id': i.id,
                    'name': i.name_snapshot,
                    'quantity': i.quantity,
                    'customizations': i.customizations,
                }
                for i in counter_items if not i.collected_at
            ],
            'other_counter_items': len(other_items),  # informational
            'is_mixed': order.is_mixed,
        })
    except Exception as e:
        return JsonResponse({'result': 'invalid', 'message': str(e)})


@login_required
@user_passes_test(is_kitchen_or_cafe_bar_user)
@require_POST
def kitchen_mark_collected_ajax(request, order_id):
    """
    Mark the items for THIS counter (not the whole order) as collected.
    If all items across all counters are then collected, the order itself
    becomes 'collected'.
    """
    order = get_object_or_404(Order, pk=order_id)
    scanner_counter = request.POST.get('counter', '') or (json.loads(request.body or '{}').get('counter', ''))
    if not scanner_counter:
        return JsonResponse({'success': False, 'message': 'counter required'})

    now = timezone.now()
    counter_items = order.items.filter(
        menu_type_snapshot=scanner_counter, collected_at__isnull=True,
    )
    # Fallback: if menu_type_snapshot wasn't set (legacy orders), use menu_item.menu_type.
    if not counter_items.exists():
        counter_items = order.items.filter(
            menu_item__menu_type=scanner_counter, collected_at__isnull=True,
        )

    updated = counter_items.update(collected_at=now)
    if updated == 0:
        return JsonResponse({'success': False, 'message': 'Nothing to collect at this counter'})

    # Is the entire order now collected?
    all_collected = not order.items.filter(collected_at__isnull=True).exists()
    if all_collected:
        order.status = 'collected'
        order.collected_at = now
        order.qr_used = True
        order.qr_used_at = now
        order.save(update_fields=['status', 'collected_at', 'qr_used', 'qr_used_at'])
        QRScanLog.objects.filter(order=order, result='valid').update(notes='Marked collected')
        _broadcast_order(order, 'collected')
    else:
        # Partial — broadcast as still-ready so the TV/kitchen reflects.
        _broadcast_order(order, 'partial_collected')

    return JsonResponse({
        'success': True,
        'order_number': order.order_number,
        'fully_collected': all_collected,
        'counter': scanner_counter,
    })


# ─── Public terminal payment completion (cafe bar) ──────────────────────────

@login_required
@user_passes_test(is_cafe_bar_user)
@require_POST
def cafe_bar_complete_payment_ajax(request, order_id):
    """
    Cafe bar staff calls this after accepting cash/card for a public order.
    Marks payment received, activates the order for the kitchen/bar, and
    returns the signed collection token so the cafe bar can print the
    collection slip for the customer.
    """
    order = get_object_or_404(Order, pk=order_id, is_public=True)
    if order.payment_received_at:
        return JsonResponse({'success': False, 'message': 'Payment already recorded'})

    with transaction.atomic():
        order.payment_received_at = timezone.now()
        order.payment_received_by = request.user
        order.status = 'ready'  # ready for collection immediately on payment
        order.confirmed_at = timezone.now()
        order.ready_at = timezone.now()
        # Ensure collection QR exists.
        if not order.qr_token:
            order.qr_token = sign_order_qr(order)
        order.save(update_fields=[
            'payment_received_at', 'payment_received_by',
            'status', 'confirmed_at', 'ready_at', 'qr_token',
        ])

    _broadcast_order(order, 'created')

    # Return the printable collection receipt URL.
    return JsonResponse({
        'success': True,
        'order_number': order.order_number,
        'collection_receipt_url': f'/cafeteria/public/ticket/{order.id}/print/',
    })


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
                is_vegetarian=request.POST.get('is_vegetarian') == 'on',
                display_order=int(request.POST.get('display_order') or 0),
                photo=request.FILES.get('photo'),
                customizations=json.loads(request.POST.get('customizations_json') or '[]'),
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
        item.is_vegetarian = request.POST.get('is_vegetarian') == 'on'
        item.display_order = int(request.POST.get('display_order') or 0)
        item.customizations = json.loads(request.POST.get('customizations_json') or '[]')
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

    items = list(MenuItem.objects.all().order_by('menu_type', 'display_order', 'name'))
    for item in items:
        item.sold_today = max(0, item.daily_quantity - item.quantity_remaining)
    return render(request, 'cafeteria/admin_stock.html', {'items': items})


@login_required
@user_passes_test(is_admin)
def admin_orders_view(request):
    """Order management / cancellation."""
    status_filter = request.GET.get('status', '')
    qs = Order.objects.all().select_related('customer').prefetch_related('items', 'items__menu_item')
    if status_filter:
        qs = qs.filter(status=status_filter)
    orders = list(qs[:100])

    # Attach counter_types — the distinct per-counter menu types an order
    # actually touches. Mixed orders show a badge for each counter; single
    # orders show one.
    for o in orders:
        seen = []
        for it in o.items.all():
            t = it.menu_type_snapshot or (it.menu_item.menu_type if it.menu_item else '')
            if t and t not in seen:
                seen.append(t)
        o.counter_types = seen or [o.menu_type]

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

    _broadcast_order(order, 'cancelled')
    return JsonResponse({'success': True, 'message': f'Order {order.order_number} cancelled, credits reinstated.'})


@login_required
@user_passes_test(is_admin)
def admin_qr_logs_view(request):
    """QR scan audit log."""
    logs = QRScanLog.objects.all().select_related('order', 'scanned_by')[:200]
    return render(request, 'cafeteria/admin_qr_logs.html', {'logs': logs})


# ─── TV Displays (polled via AJAX) ───────────────────────────────────────────

def tv_kitchen_queue_view(request):
    """43" TV: displays all kitchen orders (H + N + P prefix). No auth."""
    return render(request, 'cafeteria/tv_kitchen_queue.html')


def tv_cafe_bar_view(request):
    """43" TV: displays Cafe Bar orders (C prefix). No auth."""
    return render(request, 'cafeteria/tv_cafe_bar.html')


def tv_queue_data_ajax(request):
    """AJAX: current queue state for TV displays (polled every ~3s)."""
    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    scope = request.GET.get('scope', 'kitchen')  # 'kitchen' or 'cafe_bar'

    base = Order.objects.filter(
        status__in=['confirmed', 'preparing', 'ready'],
        created_at__gte=today_start,
    )
    if scope == 'cafe_bar':
        qs = base.filter(
            Q(menu_type='cafe_bar') | Q(items__menu_type_snapshot='cafe_bar')
        )
    else:
        qs = base.filter(
            Q(menu_type__in=['halal', 'non_halal']) |
            Q(items__menu_type_snapshot__in=['halal', 'non_halal'])
        )
    orders = qs.distinct().prefetch_related('items').order_by('created_at')

    def ser(o):
        return {
            'id': o.id,
            'order_number': o.order_number,
            'status': o.status,
            'is_public': o.is_public,
            'menu_type': o.menu_type,
            'menu_label': o.get_menu_type_display(),
            'items': [{'name': i.name_snapshot, 'qty': i.quantity} for i in o.items.all()],
            'collection_time_minutes': o.collection_time_minutes,
        }

    return JsonResponse({
        'preparing': [ser(o) for o in orders if o.status in ('confirmed', 'preparing')],
        'ready': [ser(o) for o in orders if o.status == 'ready'],
    })


# ─── Cafe Bar Counter View ───────────────────────────────────────────────────

@login_required
def cafe_bar_counter_view(request):
    """
    Split-layout Cafe Bar counter: incoming | ready.
    Also shows pending-payment orders (public terminal payment flow).
    Includes mixed orders with cafe_bar items.
    Access: admin + cafe_bar users.
    """
    if not _user_can_scan_counter(request.user, 'cafe_bar'):
        return render(request, 'cafeteria/access_denied.html', {
            'required_role': 'Cafe Bar Counter',
        }, status=403)
    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    # Orders pending payment (public terminal flow) — cafe bar processes these.
    pending_payment = Order.objects.filter(
        is_public=True, payment_method='terminal',
        payment_received_at__isnull=True,
        status='pending',
        created_at__gte=today_start,
    ).prefetch_related('items').order_by('created_at')

    # All active cafe bar orders with at least one UNCOLLECTED cafe_bar item.
    # Mixed orders whose cafe_bar items are already collected must drop off
    # this counter even if kitchen items remain uncollected.
    uncollected_cafe_items = OrderItem.objects.filter(
        order=OuterRef('pk'),
        collected_at__isnull=True,
    ).filter(
        Q(menu_type_snapshot='cafe_bar')
        | Q(menu_type_snapshot='', menu_item__menu_type='cafe_bar')
    )
    ready = Order.objects.filter(
        status__in=['confirmed', 'preparing', 'ready'],
        created_at__gte=today_start,
    ).annotate(
        _has_uncollected_cafe=Exists(uncollected_cafe_items),
    ).filter(
        _has_uncollected_cafe=True,
    ).prefetch_related('items', 'items__menu_item').order_by('created_at')

    for order in ready:
        order.counter_items = [
            i for i in order.items.all()
            if (i.menu_type_snapshot or (i.menu_item.menu_type if i.menu_item else '')) == 'cafe_bar'
               and i.collected_at is None
        ]

    return render(request, 'cafeteria/cafe_bar_counter.html', {
        'ready': ready,
        'pending_payment': pending_payment,
    })


# ─── Staff Portal (mobile PWA, 5 tabs) ───────────────────────────────────────

@login_required
def staff_portal_home_view(request):
    """Staff Portal: Home tab with credit balance, vending QR, and recent orders."""
    user = request.user
    recent = Order.objects.filter(customer=user).order_by('-created_at')[:5]
    active = Order.objects.filter(
        customer=user,
        status__in=['confirmed', 'preparing', 'ready'],
    ).order_by('-created_at').first()

    # Unique staff vending QR — shown on the home page for cafeteria
    # vending machines to scan.
    vending_token = sign_staff_vending_qr(user)
    vending_qr = _generate_qr_image_base64(vending_token, box_size=5)

    return render(request, 'cafeteria/staff_portal_home.html', {
        'user': user,
        'recent': recent,
        'active': active,
        'vending_qr': vending_qr,
    })


@login_required
def staff_portal_order_view(request):
    """Staff Portal: Order tab — browse menu, add to cart (mobile)."""
    halal = MenuItem.objects.filter(menu_type='halal', is_available=True).order_by('display_order', 'name')
    non_halal = MenuItem.objects.filter(menu_type='non_halal', is_available=True).order_by('display_order', 'name')
    cafe = MenuItem.objects.filter(menu_type='cafe_bar', is_available=True).order_by('display_order', 'name')
    return render(request, 'cafeteria/staff_portal_order.html', {
        'user': request.user,
        'halal_items': halal, 'non_halal_items': non_halal, 'cafe_items': cafe,
        'tabs': {'halal': halal, 'non_halal': non_halal, 'cafe_bar': cafe},
    })


@login_required
def staff_portal_qr_view(request):
    """Staff Portal: active QR codes for collection."""
    user = request.user
    active_orders = Order.objects.filter(
        customer=user,
        status__in=['confirmed', 'preparing', 'ready'],
        qr_used=False,
    ).prefetch_related('items').order_by('-created_at')

    # Pre-generate QR images.
    qrs = []
    for o in active_orders:
        qrs.append({
            'order': o,
            'qr_image': _generate_qr_image_base64(o.qr_token, box_size=6),
        })
    return render(request, 'cafeteria/staff_portal_qr.html', {'qrs': qrs})


@login_required
def staff_portal_history_view(request):
    """Staff Portal: order history + vending transactions."""
    orders = Order.objects.filter(customer=request.user).prefetch_related('items').order_by('-created_at')[:50]
    vending_txns = CreditTransaction.objects.filter(
        user=request.user, type='vending',
    ).order_by('-created_at')[:50]
    return render(request, 'cafeteria/staff_portal_history.html', {
        'orders': orders,
        'vending_txns': vending_txns,
    })


@login_required
def staff_portal_profile_view(request):
    """Staff Portal: profile (credit, PIN, face ID toggle)."""
    from django.db.models import Sum
    if request.method == 'POST':
        new_pin = (request.POST.get('kiosk_pin') or '').strip()
        if new_pin:
            request.user.kiosk_pin = new_pin
            request.user.save(update_fields=['kiosk_pin'])
            messages.success(request, 'PIN updated.')
        return redirect('staff_portal_profile')

    # Month's spend
    month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_spent = CreditTransaction.objects.filter(
        user=request.user, type='order', created_at__gte=month_start,
    ).aggregate(total=Sum('amount'))['total'] or 0
    month_spent = abs(month_spent)

    return render(request, 'cafeteria/staff_portal_profile.html', {
        'user': request.user,
        'month_spent': month_spent,
    })


# ─── Public Walk-In Ordering ────────────────────────────────────────────────

def public_order_view(request, menu_type):
    """
    Public walk-in menu browsing. No login. Uses public_price.
    Payment stub: records order as 'confirmed' with payment_method='cash'
    (real Stripe/PayNow wiring in _attempt_payment).
    """
    if menu_type not in ('kitchen', 'cafe_bar'):
        raise Http404()

    if menu_type == 'kitchen':
        items_by_type = {
            'halal': MenuItem.objects.filter(menu_type='halal', is_available=True).order_by('display_order', 'name'),
            'non_halal': MenuItem.objects.filter(menu_type='non_halal', is_available=True).order_by('display_order', 'name'),
        }
    else:
        items_by_type = {
            'cafe_bar': MenuItem.objects.filter(menu_type='cafe_bar', is_available=True).order_by('display_order', 'name'),
        }

    return render(request, 'cafeteria/public_order.html', {
        'menu_type': menu_type,
        'items_by_type': items_by_type,
        'idle_timeout': KioskConfig.get().idle_session_seconds,
    })


@require_POST
def public_place_order_ajax(request):
    """
    Place a public walk-in order. Supports:
    - Mixed carts (kitchen + cafe bar items)
    - payment_method = 'stripe' or 'paynow' (pay at kiosk)
    - payment_method = 'terminal' (generates payment QR to pay at cafe bar)
    For terminal: order is created with status='pending_payment' and a
    payment_token QR. Only becomes 'confirmed' (and items reserved) after
    cafe bar scans the QR and accepts cash/card.
    """
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        customer_name = (data.get('public_name') or 'Walk-in').strip()
        payment_method = data.get('payment_method', 'terminal')

        if not items_data:
            return JsonResponse({'success': False, 'message': 'Cart is empty'})

        with transaction.atomic():
            item_ids = [int(i.get('id')) for i in items_data]
            menu_items = {mi.id: mi for mi in MenuItem.objects.select_for_update().filter(id__in=item_ids)}

            subtotal = Decimal('0')
            buf = []
            menu_types_in_cart = set()
            for raw in items_data:
                mid = int(raw.get('id'))
                qty = int(raw.get('quantity', 1))
                cust = raw.get('customizations', {})
                mi = menu_items.get(mid)
                if not mi or not mi.is_available:
                    return JsonResponse({'success': False, 'message': 'Item unavailable'})
                if mi.quantity_remaining < qty:
                    return JsonResponse({'success': False, 'message': f'{mi.name}: only {mi.quantity_remaining} left'})
                price = mi.public_price
                subtotal += price * qty
                mi.quantity_remaining -= qty
                mi.save(update_fields=['quantity_remaining'])
                menu_types_in_cart.add(mi.menu_type)
                buf.append({
                    'menu_item': mi, 'name': mi.name, 'price': price,
                    'qty': qty, 'cust': cust, 'menu_type': mi.menu_type,
                })

            is_mixed = len(menu_types_in_cart) > 1
            order_menu_type = 'mixed' if is_mixed else next(iter(menu_types_in_cart))

            # Determine initial status based on payment method.
            if payment_method == 'terminal':
                initial_status = 'pending'  # awaiting cafe bar payment
                confirmed_at = None
            elif payment_method == 'stripe':
                initial_status = 'pending'  # confirmed by webhook
                confirmed_at = None
            elif payment_method == 'paynow':
                initial_status = 'pending'  # trust paynow QR scan (no webhook)
                confirmed_at = None
            else:  # cash (legacy)
                initial_status = 'ready'
                confirmed_at = timezone.now()

            order = Order.objects.create(
                order_number=Order.next_number(
                    order_menu_type, is_public=True, is_mixed=is_mixed
                ),
                customer=None,
                is_public=True,
                public_name=customer_name,
                menu_type=order_menu_type,
                is_mixed=is_mixed,
                status=initial_status,
                subtotal=subtotal,
                credits_applied=Decimal('0'),
                balance_due=subtotal,
                payment_method=payment_method,
                confirmed_at=confirmed_at,
            )
            # Collection QR (used after payment completes).
            order.qr_token = sign_order_qr(order)
            # Payment QR (used by terminal-payment flow only).
            if payment_method == 'terminal':
                from django.core.signing import TimestampSigner
                signer = TimestampSigner(salt='payment-qr')
                order.payment_token = signer.sign(f'pay-{order.id}')
            order.save(update_fields=['qr_token', 'payment_token'])

            for b in buf:
                OrderItem.objects.create(
                    order=order,
                    menu_item=b['menu_item'],
                    name_snapshot=b['name'],
                    price_snapshot=b['price'],
                    quantity=b['qty'],
                    customizations=b['cust'],
                    subtotal=b['price'] * b['qty'],
                    menu_type_snapshot=b['menu_type'],
                )

            # For Stripe, generate checkout session.
            if payment_method == 'stripe':
                from .payments import create_stripe_checkout_session
                sess = create_stripe_checkout_session(
                    subtotal, customer_name, {'order_id': str(order.id)}
                )
                if sess:
                    return JsonResponse({
                        'success': True, 'order_id': order.id, 'order_number': order.order_number,
                        'checkout_url': sess['url'],
                    })

            # For PayNow, return QR for balance.
            if payment_method == 'paynow':
                from .payments import build_paynow_qr
                qr = build_paynow_qr(subtotal, reference=f'Order-{order.order_number}')
                return JsonResponse({
                    'success': True, 'order_id': order.id, 'order_number': order.order_number,
                    'paynow_qr': qr, 'balance_due': str(subtotal),
                })

        # Optional email receipt (async via Celery if available).
        if data.get('email'):
            try:
                from .tasks import send_order_email_async
                if send_order_email_async.delay:
                    send_order_email_async.delay(order.id, data['email'])
                else:
                    raise RuntimeError('no-celery')
            except Exception:
                from .emails import send_order_receipt
                send_order_receipt(order, data['email'])

        # Broadcast to kitchen + TV + admin.
        _broadcast_order(order, 'created')

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'redirect': f'/cafeteria/public/ticket/{order.id}/',
        })
    except Exception as e:
        import logging
        logging.exception('public_place_order_ajax')
        return JsonResponse({'success': False, 'message': str(e)})


def public_ticket_view(request, order_id):
    """
    Public order ticket:
    - If payment still pending (terminal flow): show PAYMENT QR + instructions
    - If paid: show COLLECTION QR.
    Both include full item details for printing.
    """
    order = get_object_or_404(Order, pk=order_id, is_public=True)

    # Determine which QR to show.
    is_pending = order.payment_method == 'terminal' and not order.payment_received_at
    if is_pending and order.payment_token:
        qr_image = _generate_qr_image_base64(order.payment_token, box_size=8)
        qr_kind = 'payment'
    else:
        qr_image = _generate_qr_image_base64(order.qr_token, box_size=8)
        qr_kind = 'collection'

    return render(request, 'cafeteria/public_ticket.html', {
        'order': order,
        'qr_image': qr_image,
        'qr_kind': qr_kind,
        'autoprint': request.GET.get('autoprint') == '1',
        'escpos_b64': _escpos_receipt_b64(order) if qr_kind == 'collection' else '',
    })


# ─── Admin Dashboard + Reports ───────────────────────────────────────────────


@login_required
@user_passes_test(is_admin)
def admin_my_orders_view(request):
    """Admin's own 'My Orders' — standalone admin UI (not the staff PWA)."""
    user = request.user
    active_orders = Order.objects.filter(
        customer=user,
        status__in=['confirmed', 'preparing', 'ready'],
        qr_used=False,
    ).prefetch_related('items').order_by('-created_at')

    qrs = []
    for o in active_orders:
        qrs.append({
            'order': o,
            'qr_image': _generate_qr_image_base64(o.qr_token, box_size=6),
        })

    recent = Order.objects.filter(customer=user).prefetch_related('items').order_by('-created_at')[:20]

    return render(request, 'cafeteria/admin_my_orders.html', {
        'qrs': qrs,
        'recent': recent,
    })


@login_required
@user_passes_test(is_admin)
def admin_new_order_view(request):
    """Admin order placement — uses admin base layout so nav stays accessible."""
    halal = MenuItem.objects.filter(menu_type='halal', is_available=True).order_by('display_order', 'name')
    non_halal = MenuItem.objects.filter(menu_type='non_halal', is_available=True).order_by('display_order', 'name')
    cafe = MenuItem.objects.filter(menu_type='cafe_bar', is_available=True).order_by('display_order', 'name')
    return render(request, 'cafeteria/admin_new_order.html', {
        'halal_items': halal,
        'non_halal_items': non_halal,
        'cafe_items': cafe,
        'tabs': {'halal': halal, 'non_halal': non_halal, 'cafe_bar': cafe},
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_hours_view(request):
    """Admin: operating hours (per menu + weekday) and holiday calendar."""
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'save_hours':
            # Expect a list of existing row ids + corresponding fields.
            row_ids = request.POST.getlist('id')
            for rid in row_ids:
                try:
                    row = OrderingHours.objects.get(pk=int(rid))
                except (ValueError, OrderingHours.DoesNotExist):
                    continue
                row.menu_type = request.POST.get(f'menu_type_{rid}', row.menu_type)
                row.label = request.POST.get(f'label_{rid}', '')[:40]
                row.opens_at = request.POST.get(f'opens_at_{rid}', row.opens_at) or row.opens_at
                row.closes_at = request.POST.get(f'closes_at_{rid}', row.closes_at) or row.closes_at
                row.is_active = request.POST.get(f'is_active_{rid}') == 'on'
                for d in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'):
                    setattr(row, d, request.POST.get(f'{d}_{rid}') == 'on')
                row.save()
            messages.success(request, 'Operating hours saved.')
            return redirect('cafeteria_admin_hours')

        if action == 'add_hours':
            try:
                OrderingHours.objects.create(
                    menu_type=request.POST.get('new_menu_type', 'kitchen'),
                    label=request.POST.get('new_label', '')[:40],
                    opens_at=request.POST.get('new_opens_at') or '08:00',
                    closes_at=request.POST.get('new_closes_at') or '17:00',
                    is_active=True,
                    mon=True, tue=True, wed=True, thu=True, fri=True,
                    sat=False, sun=False,
                )
                messages.success(request, 'Window added (Mon–Fri by default).')
            except Exception as e:
                messages.error(request, f'Could not add window: {e}')
            return redirect('cafeteria_admin_hours')

        if action == 'delete_hours':
            try:
                OrderingHours.objects.filter(pk=int(request.POST.get('id'))).delete()
                messages.success(request, 'Window removed.')
            except (TypeError, ValueError):
                pass
            return redirect('cafeteria_admin_hours')

        if action == 'add_holiday':
            d = request.POST.get('holiday_date')
            label = (request.POST.get('holiday_label') or '').strip()[:100]
            scope = request.POST.get('holiday_scope', 'all')
            if d and label and scope in ('all', 'kitchen', 'cafe_bar'):
                Holiday.objects.update_or_create(
                    date=d,
                    defaults={'label': label, 'scope': scope},
                )
                messages.success(request, f'Holiday "{label}" saved.')
            else:
                messages.error(request, 'Date and label are required.')
            return redirect('cafeteria_admin_hours')

        if action == 'delete_holiday':
            try:
                Holiday.objects.filter(pk=int(request.POST.get('id'))).delete()
                messages.success(request, 'Holiday removed.')
            except (TypeError, ValueError):
                pass
            return redirect('cafeteria_admin_hours')

    hours = OrderingHours.objects.all().order_by('menu_type', 'opens_at')
    holidays = Holiday.objects.filter(date__gte=timezone.localdate()).order_by('date')
    past_holidays = Holiday.objects.filter(date__lt=timezone.localdate()).order_by('-date')[:10]
    return render(request, 'cafeteria/admin_hours.html', {
        'hours': hours,
        'holidays': holidays,
        'past_holidays': past_holidays,
        'today': timezone.localdate(),
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_kiosk_config_view(request):
    """Admin: edit kiosk idle / post-print timeouts and credit working days."""
    cfg = KioskConfig.get()
    if request.method == 'POST':
        try:
            landing = int(request.POST.get('idle_landing_seconds') or cfg.idle_landing_seconds)
            session_s = int(request.POST.get('idle_session_seconds') or cfg.idle_session_seconds)
            post_print = int(request.POST.get('post_print_seconds') or cfg.post_print_seconds)
            working_days = int(request.POST.get('credit_working_days') or cfg.credit_working_days)
            # Sane bounds.
            cfg.idle_landing_seconds = max(5, min(600, landing))
            cfg.idle_session_seconds = max(5, min(600, session_s))
            cfg.post_print_seconds = max(1, min(120, post_print))
            cfg.credit_working_days = max(1, min(31, working_days))
            cfg.save()
            messages.success(request, 'Settings updated.')
        except (TypeError, ValueError):
            messages.error(request, 'Please enter whole numbers only.')
        return redirect('cafeteria_kiosk_config')
    return render(request, 'cafeteria/admin_kiosk_config.html', {'cfg': cfg})


@login_required
@user_passes_test(is_admin)
def cafeteria_dashboard_view(request):
    """Admin KPI dashboard for cafeteria."""
    from django.db.models import Sum, Count
    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timezone.timedelta(days=6)

    today_orders = Order.objects.filter(created_at__gte=today_start, status__in=['confirmed', 'preparing', 'ready', 'collected'])
    today_revenue = today_orders.aggregate(s=Sum('subtotal'))['s'] or 0
    today_credits = today_orders.aggregate(s=Sum('credits_applied'))['s'] or 0
    today_count = today_orders.count()
    today_refunds = Order.objects.filter(cancelled_at__gte=today_start).count()

    # Revenue by day (last 7 days)
    daily = []
    for i in range(6, -1, -1):
        d_start = today_start - timezone.timedelta(days=i)
        d_end = d_start + timezone.timedelta(days=1)
        rev = Order.objects.filter(
            created_at__gte=d_start, created_at__lt=d_end,
            status__in=['confirmed', 'preparing', 'ready', 'collected'],
        ).aggregate(s=Sum('subtotal'))['s'] or 0
        daily.append({'date': d_start, 'revenue': float(rev)})

    # Top 5 items this week
    top_items = (
        OrderItem.objects.filter(order__created_at__gte=week_start)
        .values('name_snapshot')
        .annotate(total=Sum('quantity'))
        .order_by('-total')[:5]
    )

    recent_orders = Order.objects.select_related('customer').order_by('-created_at')[:10]

    return render(request, 'cafeteria/admin_dashboard.html', {
        'today_revenue': today_revenue,
        'today_credits': today_credits,
        'today_count': today_count,
        'today_refunds': today_refunds,
        'daily': daily,
        'daily_max': max([d['revenue'] for d in daily] + [1]),
        'top_items': top_items,
        'recent_orders': recent_orders,
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_reports_view(request):
    """Revenue reports (daily/weekly/monthly) including vending."""
    from django.db.models import Sum, Count
    period = request.GET.get('period', 'week')  # 'day', 'week', 'month'
    now = timezone.localtime()
    if period == 'day':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timezone.timedelta(days=7)

    orders = Order.objects.filter(
        created_at__gte=start,
        status__in=['confirmed', 'preparing', 'ready', 'collected'],
    )
    refunded = Order.objects.filter(cancelled_at__gte=start)

    totals = {
        'revenue': orders.aggregate(s=Sum('subtotal'))['s'] or 0,
        'credits': orders.aggregate(s=Sum('credits_applied'))['s'] or 0,
        'refunds': refunded.aggregate(s=Sum('subtotal'))['s'] or 0,
    }
    totals['net'] = totals['revenue'] - totals['refunds']

    by_menu = {}
    menu_labels = {'halal': 'Local Kitchen', 'non_halal': 'International Kitchen', 'cafe_bar': 'Cafe Bar', 'mixed': 'Mixed'}
    for mt in ['halal', 'non_halal', 'cafe_bar', 'mixed']:
        data = orders.filter(menu_type=mt).aggregate(
            revenue=Sum('subtotal'), count=Count('id')
        )
        by_menu[menu_labels[mt]] = data

    by_payment = {}
    payment_labels = {'credits': 'Staff Credits', 'stripe': 'Stripe Card', 'paynow': 'PayNow QR', 'cash': 'Cash', 'terminal': 'Terminal', 'mixed': 'Credits + Card/PayNow'}
    for p in ['credits', 'stripe', 'paynow', 'cash', 'terminal', 'mixed']:
        data = orders.filter(payment_method=p).aggregate(
            revenue=Sum('subtotal'), count=Count('id')
        )
        by_payment[payment_labels[p]] = data

    # Daily breakdown
    daily_rows = []
    days = 7 if period == 'week' else (30 if period == 'month' else 1)
    for i in range(days - 1, -1, -1):
        d_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timezone.timedelta(days=i)
        d_end = d_start + timezone.timedelta(days=1)
        day_orders = Order.objects.filter(created_at__gte=d_start, created_at__lt=d_end)
        daily_rows.append({
            'date': d_start,
            'orders': day_orders.count(),
            'revenue': day_orders.aggregate(s=Sum('subtotal'))['s'] or 0,
        })

    # ── Vending summary for this period ───────────────────────────
    vending_qs = CreditTransaction.objects.filter(
        type='vending', status='success', created_at__gte=start,
    )
    vending_total = abs(vending_qs.aggregate(s=Sum('amount'))['s'] or 0)
    vending_count = vending_qs.count()
    vending_failed = CreditTransaction.objects.filter(
        type='vending', status='failed', created_at__gte=start,
    ).count()

    # Per-machine breakdown
    vending_machines = (
        vending_qs.values('machine_id')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    vending_machine_rows = []
    for m in vending_machines:
        vending_machine_rows.append({
            'id': m['machine_id'] or '(unknown)',
            'count': m['count'],
            'total': abs(m['total'] or 0),
        })

    return render(request, 'cafeteria/admin_reports.html', {
        'period': period,
        'totals': totals,
        'by_menu': by_menu,
        'by_payment': by_payment,
        'daily_rows': daily_rows,
        'vending_total': vending_total,
        'vending_count': vending_count,
        'vending_failed': vending_failed,
        'vending_machine_rows': vending_machine_rows,
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_refunds_view(request):
    """Refund trail."""
    cancelled = Order.objects.filter(cancelled_at__isnull=False).select_related('customer').order_by('-cancelled_at')[:100]
    return render(request, 'cafeteria/admin_refunds.html', {'refunds': cancelled})


@login_required
@user_passes_test(is_admin)
def cafeteria_staff_view(request):
    """Compact list view of staff with search, role filter and pagination."""
    from django.core.paginator import Paginator
    qs = visible_staff_qs(request.user).filter(is_active=True)

    q = (request.GET.get('q') or '').strip()
    role_f = (request.GET.get('role') or '').strip()

    if q:
        qs = qs.filter(
            Q(staff_id__icontains=q)
            | Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(department__icontains=q)
        )
    if role_f in ('admin', 'kitchen', 'cafe_bar'):
        qs = qs.filter(role=role_f)
    elif role_f == 'staff':
        qs = qs.filter(Q(role='') | Q(role__isnull=True))

    qs = qs.order_by('staff_id')
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'cafeteria/admin_staff.html', {
        'staff': page.object_list,
        'page_obj': page,
        'paginator': paginator,
        'q': q,
        'role_filter': role_f,
        'total_count': paginator.count,
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def cafeteria_staff_adjust_credit_ajax(request, user_id):
    """Admin: adjust a staff member's credit balance."""
    user = get_object_or_404(StaffUser, pk=user_id)
    # Non-root admins cannot touch root users (pretend doesn't exist).
    if user.is_root and not getattr(request.user, 'is_root', False):
        raise Http404()
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        notes = request.POST.get('notes', 'Admin adjustment')
        with transaction.atomic():
            user.credit_balance += amount
            user.save(update_fields=['credit_balance'])
            CreditTransaction.objects.create(
                user=user, type='admin_adjust', amount=amount,
                balance_after=user.credit_balance, notes=notes,
            )
        return JsonResponse({'success': True, 'new_balance': str(user.credit_balance)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ─── Stripe return URLs + webhook ────────────────────────────────────────────

def stripe_success_view(request):
    """Customer lands here after successful Stripe Checkout."""
    session_id = request.GET.get('session_id', '')
    return render(request, 'cafeteria/stripe_success.html', {'session_id': session_id})


from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    """
    Stripe sends payment confirmations here.
    Set endpoint in Stripe Dashboard: https://<domain>/cafeteria/stripe/webhook/
    """
    import logging
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    if not webhook_secret:
        logging.warning('Stripe webhook hit but STRIPE_WEBHOOK_SECRET not set')
        return JsonResponse({'ok': True})

    try:
        import stripe
        stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        logging.exception('Stripe webhook signature verification failed')
        return JsonResponse({'error': str(e)}, status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        order_id = (session.get('metadata') or {}).get('order_id')
        if order_id:
            try:
                order = Order.objects.get(pk=int(order_id))
                order.status = 'ready'
                order.confirmed_at = timezone.now()
                order.ready_at = timezone.now()
                order.save(update_fields=['status', 'confirmed_at', 'ready_at'])
                _broadcast_order(order, 'ready')
            except Order.DoesNotExist:
                pass

    return JsonResponse({'ok': True})


# ─── Vending Machine Admin Reports ───────────────────────────────────────────


@login_required
@user_passes_test(is_admin)
def admin_vending_report_view(request):
    """
    Admin: Vending machine transaction report.
    Filters: month (YYYY-MM), machine_id, status.
    Shows KPIs, per-machine breakdown, transaction list, and CSV download link.
    """
    from django.db.models import Sum, Count
    import calendar as _cal

    now = timezone.localtime()

    # ── Parse month filter ────────────────────────────────────────
    month_str = request.GET.get('month', '')
    try:
        year, month = int(month_str[:4]), int(month_str[5:7])
    except (ValueError, IndexError):
        year, month = now.year, now.month

    _, days_in = _cal.monthrange(year, month)
    start = timezone.make_aware(
        timezone.datetime(year, month, 1),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        timezone.datetime(year, month, days_in, 23, 59, 59),
        timezone.get_current_timezone(),
    )

    # Filter params
    machine_filter = request.GET.get('machine', '').strip()
    status_filter = request.GET.get('status', '').strip()

    qs = CreditTransaction.objects.filter(
        type='vending',
        created_at__gte=start,
        created_at__lte=end,
    ).select_related('user')

    if machine_filter:
        qs = qs.filter(machine_id=machine_filter)
    if status_filter in ('success', 'failed'):
        qs = qs.filter(status=status_filter)

    # ── KPIs ──────────────────────────────────────────────────────
    success_qs = qs.filter(status='success')
    failed_qs = qs.filter(status='failed')

    total_deducted = abs(success_qs.aggregate(s=Sum('amount'))['s'] or 0)
    total_txns = qs.count()
    success_count = success_qs.count()
    failed_count = failed_qs.count()

    # ── Per-machine breakdown ─────────────────────────────────────
    machines = (
        success_qs.values('machine_id')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    machine_rows = []
    for m in machines:
        machine_rows.append({
            'id': m['machine_id'] or '(unknown)',
            'count': m['count'],
            'total': abs(m['total'] or 0),
        })

    # ── All machines for filter dropdown ──────────────────────────
    all_machines = (
        CreditTransaction.objects.filter(type='vending')
        .exclude(machine_id='')
        .values_list('machine_id', flat=True)
        .distinct()
        .order_by('machine_id')
    )

    # ── Available months for dropdown ─────────────────────────────
    first_txn = CreditTransaction.objects.filter(type='vending').order_by('created_at').first()
    available_months = []
    if first_txn:
        cursor = first_txn.created_at.replace(day=1)
        end_cursor = now.replace(day=1)
        while cursor <= end_cursor:
            available_months.append(f'{cursor.year}-{cursor.month:02d}')
            m = cursor.month + 1
            y = cursor.year
            if m > 12:
                m = 1
                y += 1
            cursor = cursor.replace(year=y, month=m)

    txns = qs.order_by('-created_at')[:200]

    return render(request, 'cafeteria/admin_vending_report.html', {
        'month_str': f'{year}-{month:02d}',
        'month_label': f'{_cal.month_name[month]} {year}',
        'total_deducted': total_deducted,
        'total_txns': total_txns,
        'success_count': success_count,
        'failed_count': failed_count,
        'machine_rows': machine_rows,
        'txns': txns,
        'all_machines': all_machines,
        'available_months': available_months,
        'machine_filter': machine_filter,
        'status_filter': status_filter,
    })


@login_required
@user_passes_test(is_admin)
def admin_vending_csv_view(request):
    """
    Download vending transactions as CSV for a given month.
    Used by accounts team to reconcile with vendor invoices.
    """
    import csv as _csv
    import calendar as _cal
    from django.http import HttpResponse

    now = timezone.localtime()
    month_str = request.GET.get('month', '')
    try:
        year, month = int(month_str[:4]), int(month_str[5:7])
    except (ValueError, IndexError):
        year, month = now.year, now.month

    _, days_in = _cal.monthrange(year, month)
    start = timezone.make_aware(
        timezone.datetime(year, month, 1),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        timezone.datetime(year, month, days_in, 23, 59, 59),
        timezone.get_current_timezone(),
    )

    machine_filter = request.GET.get('machine', '').strip()

    qs = CreditTransaction.objects.filter(
        type='vending',
        status='success',
        created_at__gte=start,
        created_at__lte=end,
    ).select_related('user').order_by('created_at')

    if machine_filter:
        qs = qs.filter(machine_id=machine_filter)

    filename = f'vending_report_{year}_{month:02d}'
    if machine_filter:
        filename += f'_{machine_filter}'
    filename += '.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = _csv.writer(response)
    writer.writerow([
        'Date', 'Time', 'Staff ID', 'Staff Name', 'Department',
        'Machine ID', 'Description', 'Amount (SGD)', 'Balance After',
    ])

    total = Decimal('0')
    for txn in qs:
        local_dt = timezone.localtime(txn.created_at)
        amt = abs(txn.amount)
        total += amt
        writer.writerow([
            local_dt.strftime('%Y-%m-%d'),
            local_dt.strftime('%H:%M:%S'),
            txn.user.staff_id if txn.user else '',
            txn.user.full_name if txn.user else '',
            txn.user.department if txn.user else '',
            txn.machine_id,
            txn.notes,
            f'{amt:.2f}',
            f'{txn.balance_after:.2f}',
        ])

    # Summary row
    writer.writerow([])
    writer.writerow(['', '', '', '', '', '', 'TOTAL', f'{total:.2f}', ''])
    writer.writerow([f'Report: {_cal.month_name[month]} {year}'])

    return response


# ─── Vending Machine API ─────────────────────────────────────────────────────


@login_required
@user_passes_test(is_admin)
def vending_api_docs_view(request):
    """Admin: Vending Machine API documentation page."""
    api_key = getattr(settings, 'VENDING_API_KEY', '')
    if api_key:
        preview = api_key[:6] + '…' + api_key[-4:]
    else:
        preview = '(not set)'

    base_url = request.build_absolute_uri('/').rstrip('/')
    return render(request, 'cafeteria/admin_vending_api_docs.html', {
        'api_key_preview': preview,
        'api_key_set': bool(api_key),
        'base_url': base_url,
    })


@login_required
@user_passes_test(is_admin)
def vending_api_docs_download_view(request):
    """Admin: Download Vending API docs as .doc file."""
    from django.http import HttpResponse
    domain = request.get_host()
    content = render(request, 'cafeteria/vending_api_doc_download.html', {
        'domain': domain,
    }).content
    response = HttpResponse(content, content_type='application/msword')
    response['Content-Disposition'] = 'attachment; filename="Vending_Machine_API_Documentation.doc"'
    return response


@csrf_exempt
@require_POST
def vending_deduct_view(request):
    """
    External API for vending machines to deduct staff cafeteria credit.

    Authentication: Bearer token in Authorization header.
        Authorization: Bearer <VENDING_API_KEY>

    Request body (JSON):
        {
            "qr_token":    "VEND:<staff_id>.<hmac>",   // scanned from staff QR
            "amount":      2.50,                        // positive number
            "machine_id":  "VM-01",                     // machine identifier
            "description": "Canned Coffee"              // optional item description
        }

    Response (JSON):
        Success (200):
            {"success": true, "balance": 47.50, "staff_id": "EMP-001", "transaction_id": 42}

        Insufficient funds (200):
            {"success": false, "error": "insufficient_funds",
             "message": "Insufficient credit. Balance: S$1.20, required: S$2.50",
             "balance": 1.20}

        Invalid QR (200):
            {"success": false, "error": "invalid_qr", "message": "Invalid or unrecognised QR code"}

        Bad request (400):
            {"success": false, "error": "bad_request", "message": "..."}

        Unauthorized (401):
            {"success": false, "error": "unauthorized", "message": "Invalid API key"}
    """
    # ── Authenticate machine via Bearer token ─────────────────────
    api_key = getattr(settings, 'VENDING_API_KEY', '')
    if not api_key:
        return JsonResponse({'success': False, 'error': 'server_error',
                             'message': 'Vending API not configured'}, status=500)

    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth.startswith('Bearer ') or auth[7:] != api_key:
        return JsonResponse({'success': False, 'error': 'unauthorized',
                             'message': 'Invalid API key'}, status=401)

    # ── Parse request ─────────────────────────────────────────────
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'bad_request',
                             'message': 'Invalid JSON body'}, status=400)

    qr_token = (data.get('qr_token') or '').strip()
    amount_raw = data.get('amount')
    machine_id = (data.get('machine_id') or '').strip()[:50]
    description = (data.get('description') or '').strip()[:120]

    if not qr_token:
        return JsonResponse({'success': False, 'error': 'bad_request',
                             'message': 'qr_token is required'}, status=400)
    if amount_raw is None:
        return JsonResponse({'success': False, 'error': 'bad_request',
                             'message': 'amount is required'}, status=400)
    try:
        amount = Decimal(str(amount_raw)).quantize(Decimal('0.01'))
    except Exception:
        return JsonResponse({'success': False, 'error': 'bad_request',
                             'message': 'amount must be a positive number'}, status=400)
    if amount <= 0:
        return JsonResponse({'success': False, 'error': 'bad_request',
                             'message': 'amount must be greater than 0'}, status=400)

    # ── Verify QR token ───────────────────────────────────────────
    user = verify_staff_vending_qr(qr_token)
    if user is None:
        # Log the failed attempt
        CreditTransaction.objects.create(
            user_id=1,  # system placeholder — will be overwritten below if we have a user
            type='vending',
            amount=Decimal('0'),
            balance_after=Decimal('0'),
            status='failed',
            machine_id=machine_id,
            notes=f'Invalid QR: {qr_token[:40]}',
        ) if False else None  # Don't log unknown-user attempts (no user to attach)
        return JsonResponse({'success': False, 'error': 'invalid_qr',
                             'message': 'Invalid or unrecognised QR code'})

    # ── Atomic credit deduction ───────────────────────────────────
    with transaction.atomic():
        # Lock the user row to prevent race conditions
        locked_user = StaffUser.objects.select_for_update().get(pk=user.pk)
        if locked_user.credit_balance < amount:
            # Insufficient funds — log as failed
            CreditTransaction.objects.create(
                user=locked_user,
                type='vending',
                amount=-amount,
                balance_after=locked_user.credit_balance,
                status='failed',
                machine_id=machine_id,
                notes=f'Insufficient funds: {description}' if description else 'Insufficient funds',
            )
            return JsonResponse({
                'success': False,
                'error': 'insufficient_funds',
                'message': f'Insufficient credit. Balance: S${locked_user.credit_balance}, required: S${amount}',
                'balance': float(locked_user.credit_balance),
            })

        # Deduct credits
        locked_user.credit_balance -= amount
        locked_user.save(update_fields=['credit_balance'])

        # Record transaction
        txn = CreditTransaction.objects.create(
            user=locked_user,
            type='vending',
            amount=-amount,
            balance_after=locked_user.credit_balance,
            status='success',
            machine_id=machine_id,
            notes=description or 'Vending machine purchase',
        )

    return JsonResponse({
        'success': True,
        'balance': float(locked_user.credit_balance),
        'staff_id': locked_user.staff_id,
        'transaction_id': txn.id,
    })


# ─── Internal cron endpoint (for GitHub Actions scheduled tasks) ─────────────

from django.views.decorators.csrf import csrf_exempt as _csrf_exempt_cron


@_csrf_exempt_cron
def cron_reset_credits_view(request):
    """
    Triggers monthly credit reset. Protected by CRON_SECRET bearer token.

    Called DAILY by a GitHub Actions schedule at 00:01 SGT; only actually
    runs the reset when today's date in Asia/Singapore is the 1st (or
    CREDIT_RESET_DAY). Override the date check with ?force=1 for manual
    testing via workflow_dispatch.

    @csrf_exempt because the caller (GitHub Actions) can't supply a CSRF
    cookie. Auth is enforced via the Bearer token.
    """
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    expected = getattr(settings, 'CRON_SECRET', '')
    if not expected or not auth.startswith('Bearer ') or auth[7:] != expected:
        return JsonResponse({'error': 'unauthorized'}, status=403)

    today = timezone.localdate()  # uses TIME_ZONE='Asia/Singapore'
    target_day = getattr(settings, 'CREDIT_RESET_DAY', 1)
    force = request.GET.get('force') == '1'

    if today.day != target_day and not force:
        return JsonResponse({
            'ok': True,
            'skipped': True,
            'reason': f'Today SGT is day {today.day}; reset runs on day {target_day}.',
            'today_sgt': today.isoformat(),
        })

    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('reset_credits', stdout=out)

    # ── Auto-disable expired temp/intern accounts ─────────────
    expired = StaffUser.objects.filter(
        is_active=True,
        staff_type__in=['temp', 'intern'],
        contract_end_date__lt=today,
    )
    expired_count = expired.count()
    if expired_count:
        expired.update(is_active=False)

    return JsonResponse({
        'ok': True,
        'skipped': False,
        'today_sgt': today.isoformat(),
        'output': out.getvalue(),
        'expired_accounts_disabled': expired_count,
    })


@login_required
def cafeteria_displays_hub_view(request):
    """
    Central landing page listing display views the user can access.
    Filtered by role: kitchen users see kitchen views, cafe bar users
    see cafe bar views, admins see everything.
    """
    user = request.user
    can_admin = is_admin(user)
    can_kitchen = is_kitchen_user(user)
    can_cafe_bar = is_cafe_bar_user(user)
    if not (can_admin or can_kitchen or can_cafe_bar):
        return render(request, 'cafeteria/access_denied.html', {
            'required_role': 'Kitchen, Cafe Bar, or Administrator',
        }, status=403)
    return render(request, 'cafeteria/admin_displays.html', {
        'can_admin': can_admin,
        'can_kitchen': can_kitchen,
        'can_cafe_bar': can_cafe_bar,
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_credits_bulk_view(request):
    """
    Bulk update monthly credit allowance for all active staff users.
    Optionally trigger an immediate reset applying the new allowance.
    """
    if request.method == 'POST':
        try:
            new_allowance = Decimal(request.POST.get('monthly_credit') or '0')
            if new_allowance < 0:
                raise ValueError('Amount cannot be negative')
            apply_now = request.POST.get('apply_now') == 'on'

            with transaction.atomic():
                # Exclude root — bulk updates should never touch root accounts.
                users = StaffUser.objects.filter(is_active=True, is_root=False)
                updated = 0
                for u in users:
                    old_allowance = u.monthly_credit
                    u.monthly_credit = new_allowance
                    if apply_now:
                        old_balance = u.credit_balance
                        u.credit_balance = new_allowance
                        u.save(update_fields=['monthly_credit', 'credit_balance'])
                        delta = Decimal(new_allowance) - Decimal(old_balance)
                        CreditTransaction.objects.create(
                            user=u, type='allowance', amount=delta,
                            balance_after=u.credit_balance,
                            notes=f'Bulk reset: monthly S${old_allowance} → S${new_allowance}',
                        )
                    else:
                        u.save(update_fields=['monthly_credit'])
                        CreditTransaction.objects.create(
                            user=u, type='admin_adjust', amount=Decimal('0'),
                            balance_after=u.credit_balance,
                            notes=f'Monthly allowance changed: S${old_allowance} → S${new_allowance} (no balance change)',
                        )
                    updated += 1

            messages.success(
                request,
                f'Updated monthly allowance for {updated} staff to S${new_allowance}.'
                + (' Balances reset immediately.' if apply_now else ' Will apply on next monthly reset.')
            )
            return redirect('cafeteria_credits_bulk')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    # Show current state (hide root).
    staff = visible_staff_qs(request.user).filter(is_active=True).order_by('staff_id')
    distinct_allowances = staff.values_list('monthly_credit', flat=True).distinct()
    return render(request, 'cafeteria/admin_credits_bulk.html', {
        'staff': staff,
        'distinct_allowances': distinct_allowances,
        'total_staff': staff.count(),
        'credit_reset_day': getattr(settings, 'CREDIT_RESET_DAY', 1),
    })


@login_required
@user_passes_test(is_admin)
def cafeteria_credit_history_view(request, user_id=None):
    """
    Credit transaction history. If user_id is given, shows that user's
    transactions. Otherwise shows the full system-wide ledger.
    """
    qs = CreditTransaction.objects.select_related('user', 'related_order').order_by('-created_at')
    # Hide root users' transactions from non-root admins.
    if not getattr(request.user, 'is_root', False):
        qs = qs.exclude(user__is_root=True)
    target_user = None
    if user_id:
        target_user = get_object_or_404(StaffUser, pk=user_id)
        if target_user.is_root and not getattr(request.user, 'is_root', False):
            raise Http404()
        qs = qs.filter(user=target_user)
    from django.core.paginator import Paginator
    paginator = Paginator(qs, 100)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'cafeteria/admin_credit_history.html', {
        'transactions': page,
        'target_user': target_user,
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def cafeteria_staff_role_ajax(request, user_id):
    """Admin: set a staff member's workstation role."""
    user = get_object_or_404(StaffUser, pk=user_id)
    # Block non-root admins from modifying root accounts.
    if user.is_root and not getattr(request.user, 'is_root', False):
        raise Http404()
    new_role = request.POST.get('role', '')
    if new_role not in ('', 'kitchen', 'cafe_bar', 'kitchen_admin', 'admin'):
        return JsonResponse({'success': False, 'message': 'Invalid role'})
    user.role = new_role
    # If role is 'admin', also set is_staff so they can access Django admin.
    if new_role == 'admin':
        user.is_staff = True
        user.save(update_fields=['role', 'is_staff'])
    else:
        user.save(update_fields=['role'])
    return JsonResponse({'success': True, 'role': new_role or 'staff'})


# ═══ Events: Event Menus (admin + kitchen_admin CRUD) ═══════════════════════

@login_required
@user_passes_test(is_kitchen_admin)
def event_menus_list_view(request):
    """List all event menus. Editable by admin + kitchen_admin."""
    menus = EventMenu.objects.all().prefetch_related('components').order_by('display_order', 'name')
    return render(request, 'cafeteria/event_menus_list.html', {
        'menus': menus,
    })


@login_required
@user_passes_test(is_kitchen_admin)
def event_menu_add_view(request):
    return _event_menu_save(request, None)


@login_required
@user_passes_test(is_kitchen_admin)
def event_menu_edit_view(request, menu_id):
    menu = get_object_or_404(EventMenu, pk=menu_id)
    return _event_menu_save(request, menu)


def _event_menu_save(request, menu):
    """Shared add+edit view for EventMenu."""
    is_new = menu is None
    if request.method == 'POST':
        try:
            if is_new:
                menu = EventMenu()
                menu.created_by = request.user
            menu.name = (request.POST.get('name') or '').strip()[:120]
            menu.description = (request.POST.get('description') or '').strip()
            menu.price_per_pax = Decimal(request.POST.get('price_per_pax') or '0')
            menu.min_pax = int(request.POST.get('min_pax') or 10)
            menu.max_pax = int(request.POST.get('max_pax') or 200)
            menu.is_available = request.POST.get('is_available') == 'on'
            menu.is_vegetarian = request.POST.get('is_vegetarian') == 'on'
            menu.display_order = int(request.POST.get('display_order') or 0)
            if request.FILES.get('photo'):
                menu.photo = request.FILES['photo']
            if not menu.name:
                messages.error(request, 'Menu name is required.')
                raise ValueError('missing name')
            menu.save()

            # Rebuild components from POST.
            # Expected arrays: component_category[], component_name[],
            # component_description[], component_is_vegetarian_<i>
            if not is_new:
                menu.components.all().delete()
            cats = request.POST.getlist('component_category')
            names = request.POST.getlist('component_name')
            descs = request.POST.getlist('component_description')
            for idx, (cat, nm, desc) in enumerate(zip(cats, names, descs)):
                if not (cat and nm.strip()):
                    continue
                EventMenuItem.objects.create(
                    event_menu=menu,
                    category=cat,
                    name=nm.strip()[:120],
                    description=desc.strip()[:240],
                    is_vegetarian=request.POST.get(f'component_veg_{idx}') == 'on',
                    display_order=idx,
                )
            messages.success(request, f'Event menu "{menu.name}" saved.')
            return redirect('cafeteria_event_menus')
        except (ValueError, TypeError) as e:
            messages.error(request, f'Could not save: {e}')

    return render(request, 'cafeteria/event_menu_form.html', {
        'menu': menu,
        'is_new': is_new,
        'categories': EventMenuItem.CATEGORY_CHOICES,
    })


@login_required
@user_passes_test(is_kitchen_admin)
@require_POST
def event_menu_delete_view(request, menu_id):
    menu = get_object_or_404(EventMenu, pk=menu_id)
    if menu.bookings.exists():
        messages.error(request, 'Cannot delete — this menu has bookings. Mark it unavailable instead.')
        return redirect('cafeteria_event_menus')
    menu.delete()
    messages.success(request, 'Event menu deleted.')
    return redirect('cafeteria_event_menus')


# ═══ Events: Staff PWA booking flow ═══════════════════════════════════════════

@login_required
def staff_portal_events_view(request):
    """Staff PWA 'Events' tab — lists the staff member's own bookings."""
    bookings = EventBooking.objects.filter(booked_by=request.user).select_related('event_menu').order_by('-event_date')
    return render(request, 'cafeteria/staff_portal_events.html', {
        'bookings': bookings,
    })


@login_required
def staff_portal_event_new_view(request):
    """Create a new event booking. Date must be >= today + 14 days."""
    min_date = (timezone.localdate() + timezone.timedelta(days=14)).isoformat()
    menus = EventMenu.objects.filter(is_available=True).prefetch_related('components').order_by('display_order', 'name')

    if request.method == 'POST':
        try:
            menu_id = int(request.POST.get('event_menu'))
            menu = EventMenu.objects.get(pk=menu_id, is_available=True)
            event_type = request.POST.get('event_type', 'meeting')
            if event_type not in dict(EventBooking.EVENT_TYPE_CHOICES):
                raise ValueError('invalid event type')

            pax = int(request.POST.get('pax') or 0)
            if pax < menu.min_pax:
                messages.error(request, f'{menu.name} requires at least {menu.min_pax} pax.')
                raise ValueError('below min_pax')
            if pax > menu.max_pax:
                messages.error(request, f'{menu.name} allows up to {menu.max_pax} pax.')
                raise ValueError('above max_pax')

            event_date = request.POST.get('event_date')
            event_time = request.POST.get('event_time')
            if not (event_date and event_time):
                messages.error(request, 'Date and time are required.')
                raise ValueError('missing date/time')

            from datetime import date as _date
            parsed_date = _date.fromisoformat(event_date)
            earliest = timezone.localdate() + timezone.timedelta(days=14)
            if parsed_date < earliest:
                messages.error(request, f'Event date must be on or after {earliest:%d %b %Y} (min 14 days ahead).')
                raise ValueError('too soon')

            booking = EventBooking.objects.create(
                booked_by=request.user,
                event_type=event_type,
                event_menu=menu,
                pax=pax,
                event_date=parsed_date,
                event_time=event_time,
                venue=(request.POST.get('venue') or '').strip()[:200],
                notes=(request.POST.get('notes') or '').strip(),
                title=(request.POST.get('title') or '').strip()[:160],
                status='pending',
            )
            messages.success(request, f'Event booking submitted — pending admin approval. Reference #{booking.id}.')
            return redirect('staff_portal_events')
        except (EventMenu.DoesNotExist, ValueError, TypeError):
            pass

    return render(request, 'cafeteria/staff_portal_event_new.html', {
        'menus': menus,
        'min_date': min_date,
        'event_type_choices': EventBooking.EVENT_TYPE_CHOICES,
    })


@login_required
def staff_portal_event_detail_view(request, booking_id):
    """Staff can view their own booking detail."""
    booking = get_object_or_404(EventBooking, pk=booking_id, booked_by=request.user)
    return render(request, 'cafeteria/staff_portal_event_detail.html', {
        'booking': booking,
    })


@login_required
@require_POST
def staff_portal_event_cancel_view(request, booking_id):
    """Staff can cancel their own pending booking."""
    booking = get_object_or_404(EventBooking, pk=booking_id, booked_by=request.user)
    if booking.status not in ('pending', 'approved'):
        messages.error(request, 'This booking cannot be cancelled.')
    else:
        booking.status = 'cancelled'
        booking.save(update_fields=['status'])
        messages.success(request, 'Booking cancelled.')
    return redirect('staff_portal_events')


# ═══ Events: Admin approval dashboard ════════════════════════════════════════

@login_required
@user_passes_test(is_admin)
def admin_events_view(request):
    """Admin: approval queue for event bookings."""
    status_filter = request.GET.get('status', '')
    qs = EventBooking.objects.all().select_related('event_menu', 'booked_by', 'approved_by')
    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        # Default: show pending + approved upcoming
        qs = qs.exclude(status__in=['rejected', 'cancelled', 'completed'])
    bookings = qs.order_by('status', 'event_date')
    return render(request, 'cafeteria/admin_events.html', {
        'bookings': bookings,
        'status_filter': status_filter,
    })


@login_required
@user_passes_test(is_admin)
def admin_event_new_view(request):
    """
    Admin creates + auto-approves an event booking — no 14-day minimum,
    no approval queue. Used for walk-in bookings / admin-managed events.
    """
    today = timezone.localdate()
    menus = EventMenu.objects.filter(is_available=True).prefetch_related('components').order_by('display_order', 'name')

    if request.method == 'POST':
        try:
            menu = EventMenu.objects.get(pk=int(request.POST.get('event_menu')), is_available=True)
            event_type = request.POST.get('event_type', 'meeting')
            if event_type not in dict(EventBooking.EVENT_TYPE_CHOICES):
                raise ValueError('invalid event type')

            pax = int(request.POST.get('pax') or 0)
            if pax < 1:
                messages.error(request, 'Pax must be at least 1.')
                raise ValueError('pax')

            from datetime import date as _date
            event_date = _date.fromisoformat(request.POST.get('event_date'))
            event_time = request.POST.get('event_time')
            if not event_time:
                messages.error(request, 'Event time is required.')
                raise ValueError('time')

            # Optional: let admin nominate a booker (falls back to themselves).
            booker = request.user
            booker_staff_id = (request.POST.get('booker_staff_id') or '').strip()
            if booker_staff_id:
                try:
                    booker = StaffUser.objects.get(staff_id=booker_staff_id, is_active=True)
                except StaffUser.DoesNotExist:
                    messages.warning(request, f'Staff ID {booker_staff_id} not found — booking under your account.')
                    booker = request.user

            booking = EventBooking.objects.create(
                booked_by=booker,
                event_type=event_type,
                event_menu=menu,
                pax=pax,
                event_date=event_date,
                event_time=event_time,
                venue=(request.POST.get('venue') or '').strip()[:200],
                notes=(request.POST.get('notes') or '').strip(),
                title=(request.POST.get('title') or '').strip()[:160],
                # Admin-created bookings are auto-approved.
                status='approved',
                approved_by=request.user,
                approved_at=timezone.now(),
            )
            messages.success(request, f'Event #{booking.id} created and approved.')
            return redirect('cafeteria_admin_event_detail', booking_id=booking.id)
        except (EventMenu.DoesNotExist, ValueError, TypeError):
            pass

    return render(request, 'cafeteria/admin_event_new.html', {
        'menus': menus,
        'today': today.isoformat(),
        'event_type_choices': EventBooking.EVENT_TYPE_CHOICES,
    })


@login_required
@user_passes_test(is_admin)
def admin_event_detail_view(request, booking_id):
    booking = get_object_or_404(EventBooking, pk=booking_id)
    return render(request, 'cafeteria/admin_event_detail.html', {
        'booking': booking,
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_event_approve_view(request, booking_id):
    booking = get_object_or_404(EventBooking, pk=booking_id)
    if booking.status != 'pending':
        messages.error(request, 'Only pending bookings can be approved.')
    else:
        booking.status = 'approved'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save(update_fields=['status', 'approved_by', 'approved_at'])
        messages.success(request, f'Event booking #{booking.id} approved.')
    return redirect('cafeteria_admin_events')


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_event_reject_view(request, booking_id):
    booking = get_object_or_404(EventBooking, pk=booking_id)
    if booking.status != 'pending':
        messages.error(request, 'Only pending bookings can be rejected.')
    else:
        booking.status = 'rejected'
        booking.rejection_reason = (request.POST.get('reason') or '').strip()[:500]
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_at'])
        messages.success(request, f'Event booking #{booking.id} rejected.')
    return redirect('cafeteria_admin_events')


# ═══ Events: Kitchen + Cafe Bar view of approved events ═════════════════════

@login_required
@user_passes_test(is_kitchen_or_cafe_bar_user)
def kitchen_events_view(request):
    """
    Kitchen / Cafe Bar / Kitchen Admin view of APPROVED event bookings.
    Booker staff details are only visible to admin + kitchen_admin.
    Regular kitchen / cafe bar users see the event requirements (menu, pax,
    date, venue) but NOT the booker's details.
    """
    today = timezone.localdate()
    bookings = EventBooking.objects.filter(
        status='approved',
        event_date__gte=today,
    ).select_related('event_menu', 'booked_by').prefetch_related('event_menu__components').order_by('event_date', 'event_time')

    can_see_booker = is_kitchen_admin(request.user)
    return render(request, 'cafeteria/kitchen_events.html', {
        'bookings': bookings,
        'can_see_booker': can_see_booker,
    })


@login_required
@user_passes_test(is_kitchen_or_cafe_bar_user)
def kitchen_event_detail_view(request, booking_id):
    """Detail view for a single approved event booking."""
    booking = get_object_or_404(
        EventBooking.objects.select_related('event_menu', 'booked_by').prefetch_related('event_menu__components'),
        pk=booking_id, status='approved',
    )
    can_see_booker = is_kitchen_admin(request.user)
    return render(request, 'cafeteria/kitchen_event_detail.html', {
        'booking': booking,
        'can_see_booker': can_see_booker,
    })

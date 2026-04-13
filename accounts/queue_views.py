"""
Queue management views.

Pages:
  /queue/              — User's queue dashboard (generate ticket, see status)
  /queue/my-ticket/    — User's current active ticket (for phone display)
  /queue/print/<id>/   — Thermal printer-friendly layout (58mm)
  /queue/display/      — TV display (standalone, auto-refreshing)
  /queue/manage/       — Queue manager panel (admin/staff)
  /queue/api/status/   — AJAX: current queue state (for TV auto-refresh)
  /queue/api/generate/ — AJAX: generate a new ticket
  /queue/api/update/   — AJAX: update ticket status (manager)
"""
import base64
import io
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import StaffUser, QueueTicket


from django.conf import settings as django_settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired


def is_admin(user):
    return user.is_staff or user.is_superuser


def _today():
    return timezone.localdate()


def _generate_qr_base64(data: str, box_size: int = 6) -> str:
    """Generate a QR code as a base64-encoded PNG data URL."""
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


def _active_ticket_for_user(user):
    """Return the user's active (waiting or serving) ticket for today, or None."""
    return QueueTicket.objects.filter(
        user=user, date=_today(),
        status__in=['waiting', 'serving'],
    ).first()


# ─── User Queue Dashboard ────────────────────────────────────────────────────

@login_required
def queue_dashboard_view(request):
    """User's queue page — see current ticket or generate a new one."""
    user = request.user
    ticket = _active_ticket_for_user(user)
    qr_data = None
    if ticket:
        qr_data = _generate_qr_base64(f'Q{ticket.number:03d}|{user.staff_id}|{ticket.date}')

    # How many people are waiting ahead?
    ahead = 0
    if ticket and ticket.status == 'waiting':
        ahead = QueueTicket.objects.filter(
            date=_today(), status='waiting', number__lt=ticket.number
        ).count()

    context = {
        'ticket': ticket,
        'qr_data': qr_data,
        'ahead': ahead,
    }
    return render(request, 'accounts/queue_dashboard.html', context)


@login_required
def queue_my_ticket_view(request):
    """Mobile-friendly view of user's current ticket with QR code."""
    ticket = _active_ticket_for_user(request.user)
    if not ticket:
        return redirect('queue_dashboard')
    qr_data = _generate_qr_base64(
        f'Q{ticket.number:03d}|{request.user.staff_id}|{ticket.date}',
        box_size=8,
    )
    return render(request, 'accounts/queue_my_ticket.html', {
        'ticket': ticket,
        'qr_data': qr_data,
    })


@login_required
def queue_print_view(request, ticket_id):
    """58mm thermal printer-friendly layout (requires login)."""
    ticket = get_object_or_404(QueueTicket, pk=ticket_id, user=request.user)
    qr_data = _generate_qr_base64(
        f'Q{ticket.number:03d}|{request.user.staff_id}|{ticket.date}',
        box_size=5,
    )
    # Generate a signed URL for RawBT (which can't use login cookies).
    print_token = _sign_ticket_id(ticket.pk)
    return render(request, 'accounts/queue_print.html', {
        'ticket': ticket,
        'qr_data': qr_data,
        'print_token': print_token,
    })


def _sign_ticket_id(ticket_id):
    """Create a signed token for a ticket ID (for RawBT print URL)."""
    signer = TimestampSigner()
    return signer.sign(str(ticket_id))


def _verify_ticket_token(token, max_age=300):
    """Verify a signed ticket token. Returns ticket_id or None. Default 5 min expiry."""
    signer = TimestampSigner()
    try:
        value = signer.unsign(token, max_age=max_age)
        return int(value)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def queue_print_signed_view(request, token):
    """
    Public print view with a signed token — no login required.
    Used by RawBT on the Android kiosk: RawBT fetches this URL in its
    own WebView (which doesn't share browser cookies), renders the HTML,
    and sends the rendered output to the Bluetooth thermal printer.
    Token expires after 5 minutes.
    """
    ticket_id = _verify_ticket_token(token)
    if ticket_id is None:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Invalid or expired print token')

    ticket = get_object_or_404(QueueTicket, pk=ticket_id)
    qr_data = _generate_qr_base64(
        f'Q{ticket.number:03d}|{ticket.user.staff_id}|{ticket.date}',
        box_size=5,
    )
    return render(request, 'accounts/queue_print.html', {
        'ticket': ticket,
        'qr_data': qr_data,
    })


# ─── Generate Ticket (AJAX) ──────────────────────────────────────────────────

@login_required
@require_POST
def queue_generate_ajax(request):
    """Generate a new queue ticket for the current user."""
    user = request.user
    today = _today()

    # Check if user already has an active ticket.
    existing = _active_ticket_for_user(user)
    if existing:
        return JsonResponse({
            'success': False,
            'message': f'You already have an active ticket: Q{existing.number:03d}',
        })

    number = QueueTicket.next_number(today)
    ticket = QueueTicket.objects.create(
        user=user,
        number=number,
        date=today,
    )

    qr_data = _generate_qr_base64(f'Q{number:03d}|{user.staff_id}|{today}')

    return JsonResponse({
        'success': True,
        'ticket_id': ticket.pk,
        'number': number,
        'number_display': f'Q{number:03d}',
        'qr_data': qr_data,
        'message': f'Queue ticket Q{number:03d} generated!',
    })


# ─── TV Display (standalone) ─────────────────────────────────────────────────

def queue_display_view(request):
    """Standalone TV display page — no auth required. Auto-refreshes via AJAX."""
    return render(request, 'accounts/queue_display.html')


def queue_status_ajax(request):
    """AJAX: return current queue state for the TV display."""
    today = _today()
    now_serving = list(
        QueueTicket.objects.filter(date=today, status='serving')
        .select_related('user')
        .order_by('number')
        .values('id', 'number', 'user__full_name')
    )
    waiting = list(
        QueueTicket.objects.filter(date=today, status='waiting')
        .order_by('number')
        .values('id', 'number', 'user__full_name')
    )

    # Format numbers
    for t in now_serving + waiting:
        t['number_display'] = f"Q{t['number']:03d}"
        t['name'] = t.pop('user__full_name', '')

    return JsonResponse({
        'now_serving': now_serving,
        'waiting': waiting,
        'date': today.strftime('%d %B %Y'),
    })


# ─── Queue Manager (admin/staff) ─────────────────────────────────────────────

@login_required
@user_passes_test(is_admin)
def queue_manage_view(request):
    """Queue manager panel — mark tickets as serving/served."""
    today = _today()
    now_serving = QueueTicket.objects.filter(
        date=today, status='serving'
    ).select_related('user').order_by('number')
    waiting = QueueTicket.objects.filter(
        date=today, status='waiting'
    ).select_related('user').order_by('number')
    served = QueueTicket.objects.filter(
        date=today, status='served'
    ).select_related('user').order_by('-served_at')[:20]

    context = {
        'now_serving': now_serving,
        'waiting': waiting,
        'served': served,
        'today': today,
    }
    return render(request, 'accounts/queue_manage.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def queue_update_ajax(request):
    """AJAX: update a ticket's status (serving, served, cancelled)."""
    try:
        data = json.loads(request.body)
        ticket_id = data.get('ticket_id')
        new_status = data.get('status')

        if new_status not in ('serving', 'served', 'cancelled'):
            return JsonResponse({'success': False, 'message': 'Invalid status'})

        ticket = get_object_or_404(QueueTicket, pk=ticket_id, date=_today())
        ticket.status = new_status
        if new_status == 'served':
            ticket.served_at = timezone.now()
        ticket.save()

        return JsonResponse({
            'success': True,
            'message': f'Q{ticket.number:03d} marked as {new_status}',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ─── Queue Kiosk (32" Android touchscreen) ────────────────────────────────────

def queue_kiosk_view(request):
    """
    Standalone queue kiosk for a 32" Android touchscreen with a
    Bluetooth 58mm thermal printer. Flow:

    1. Face ID scan (camera auto-starts)
    2. On match → auto-generate queue ticket
    3. Show ticket with QR code + "Print" button
    4. After printing → auto-logout after KIOSK_POST_PRINT_TIMEOUT seconds
    5. If idle → auto-reset after KIOSK_IDLE_TIMEOUT seconds

    No nav bar, no other navigation. Fully self-contained loop.
    """
    context = {
        'idle_timeout': getattr(django_settings, 'KIOSK_IDLE_TIMEOUT', 15),
        'post_print_timeout': getattr(django_settings, 'KIOSK_POST_PRINT_TIMEOUT', 10),
    }
    return render(request, 'accounts/queue_kiosk.html', context)


@require_POST
def queue_kiosk_generate_ajax(request):
    """
    AJAX: generate a queue ticket for the currently logged-in kiosk user.
    Called automatically after successful face ID login in kiosk mode.
    Returns ticket data + QR code.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Not authenticated'})

    user = request.user
    today = _today()

    existing = _active_ticket_for_user(user)
    if existing:
        qr_data = _generate_qr_base64(
            f'Q{existing.number:03d}|{user.staff_id}|{today}', box_size=8
        )
        return JsonResponse({
            'success': True,
            'existing': True,
            'ticket_id': existing.pk,
            'number': existing.number,
            'number_display': f'Q{existing.number:03d}',
            'staff_name': user.display_name,
            'staff_id': user.staff_id,
            'qr_data': qr_data,
            'print_token': _sign_ticket_id(existing.pk),
            'date': today.strftime('%d %B %Y'),
            'time': timezone.localtime().strftime('%H:%M:%S'),
            'message': f'You already have ticket Q{existing.number:03d}',
        })

    number = QueueTicket.next_number(today)
    ticket = QueueTicket.objects.create(user=user, number=number, date=today)

    qr_data = _generate_qr_base64(
        f'Q{number:03d}|{user.staff_id}|{today}', box_size=8
    )

    return JsonResponse({
        'success': True,
        'existing': False,
        'ticket_id': ticket.pk,
        'number': number,
        'number_display': f'Q{number:03d}',
        'staff_name': user.display_name,
        'staff_id': user.staff_id,
        'qr_data': qr_data,
        'print_token': _sign_ticket_id(ticket.pk),
        'date': today.strftime('%d %B %Y'),
        'time': timezone.localtime().strftime('%H:%M:%S'),
        'message': f'Queue ticket Q{number:03d} generated!',
    })

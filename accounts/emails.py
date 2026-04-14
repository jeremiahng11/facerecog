"""
Email sending helpers. Works via Django's EMAIL_BACKEND (SendGrid SMTP if configured).
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_order_receipt(order, recipient_email: str) -> bool:
    """Send an email receipt for a completed order. Fails silently."""
    if not recipient_email:
        return False
    try:
        lines = [f'Order: {order.order_number}']
        lines.append(f'Customer: {order.customer.display_name if order.customer else order.public_name}')
        lines.append(f'Placed: {order.created_at.strftime("%d %b %Y %H:%M")}')
        lines.append('')
        lines.append('Items:')
        for item in order.items.all():
            lines.append(f'  {item.quantity}x {item.name_snapshot}  S${item.subtotal}')
        lines.append('')
        lines.append(f'Subtotal:    S${order.subtotal}')
        if order.credits_applied:
            lines.append(f'Credits:     -S${order.credits_applied}')
        lines.append(f'Paid:        S${order.balance_due}  ({order.get_payment_method_display() or "—"})')
        lines.append('')
        lines.append('Please show the QR code at the counter to collect your meal.')
        body = '\n'.join(lines)

        send_mail(
            subject=f'Your cafeteria order {order.order_number}',
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@cafeteria.local'),
            recipient_list=[recipient_email],
            fail_silently=True,
        )
        return True
    except Exception as e:
        logger.warning(f'send_order_receipt failed: {e}')
        return False

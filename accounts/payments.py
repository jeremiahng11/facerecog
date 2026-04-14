"""
Payment integration module.

- Stripe: uses Checkout Sessions (redirect-based, simplest to integrate).
  Requires STRIPE_SECRET_KEY env var. Falls back to stub if missing.
- PayNow: generates a real SGQR EMV QR code string (pure Python,
  no API calls). Requires PAYNOW_UEN env var.
- Cash: manual acceptance (trust operator).
- Credits: handled in views via atomic DB transaction.
"""
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)


def attempt_payment(amount: Decimal, method: str, customer: str = '', metadata: dict = None):
    """
    For inline payment decisions at order time.
    Returns {'success': bool, 'message': str, 'transaction_id': str?, ...}

    method: 'cash', 'credits', 'paynow', 'stripe'
    """
    amount = Decimal(str(amount))
    metadata = metadata or {}

    if amount <= 0:
        return {'success': True, 'message': 'No payment required', 'transaction_id': ''}

    if method == 'cash':
        return {'success': True, 'message': 'Cash accepted', 'transaction_id': f'CASH-{customer}'}

    if method == 'paynow':
        qr = build_paynow_qr(amount, reference=f'Order-{customer}')
        if qr:
            return {
                'success': True,
                'message': 'PayNow QR generated',
                'transaction_id': f'PAYNOW-{customer}',
                'qr_payload': qr,
            }
        return {'success': True, 'message': 'Stub (no PAYNOW_UEN)', 'transaction_id': f'STUB-{customer}'}

    if method == 'stripe':
        # Return a pending flag — actual order creation waits for Stripe
        # webhook confirmation. For synchronous counter use, treat as
        # accepted here and reconcile via webhook.
        sess = create_stripe_checkout_session(amount, customer, metadata)
        if sess:
            return {
                'success': True,
                'message': 'Stripe Checkout session created',
                'transaction_id': sess['id'],
                'checkout_url': sess['url'],
            }
        return {'success': True, 'message': 'Stub (no STRIPE_SECRET_KEY)', 'transaction_id': f'STUB-{customer}'}

    return {'success': False, 'message': f'Unknown payment method: {method}'}


# ─── Stripe Checkout Session ────────────────────────────────────────────────

def create_stripe_checkout_session(amount: Decimal, customer: str, metadata: dict):
    """
    Create a Stripe Checkout Session for SGD payment.
    Returns {'id': str, 'url': str} or None.
    """
    key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if not key:
        return None
    try:
        import stripe
        stripe.api_key = key
        session = stripe.checkout.Session.create(
            mode='payment',
            line_items=[{
                'price_data': {
                    'currency': 'sgd',
                    'product_data': {'name': f'Cafeteria order — {customer}'},
                    'unit_amount': int(amount * 100),
                },
                'quantity': 1,
            }],
            metadata=metadata,
            success_url=getattr(settings, 'STRIPE_SUCCESS_URL',
                                'https://example.com/cafeteria/stripe/success/?session_id={CHECKOUT_SESSION_ID}'),
            cancel_url=getattr(settings, 'STRIPE_CANCEL_URL',
                               'https://example.com/cafeteria/kiosk/'),
        )
        return {'id': session.id, 'url': session.url}
    except Exception as e:
        logger.exception(f'Stripe session create failed: {e}')
        return None


# ─── PayNow SGQR EMV generator ───────────────────────────────────────────────
# Implements the Singapore PayNow QR format (EMVCo-compliant).

def _emv_field(tag: str, value: str) -> str:
    """Encode an EMV TLV field: 2-char tag + 2-digit length + value."""
    return f'{tag}{len(value):02d}{value}'


def _crc16_ccitt(data: str) -> str:
    """Compute CRC-16/CCITT-FALSE checksum for EMV QR."""
    crc = 0xFFFF
    for byte in data.encode('utf-8'):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return f'{crc:04X}'


def build_paynow_qr(amount: Decimal, reference: str = '') -> str:
    """
    Generate an SGQR PayNow payload string. Display this string as a
    QR code using qrcode library — any SG banking app can scan it.

    Returns the full EMV QR payload string, or '' if no UEN configured.
    """
    uen = getattr(settings, 'PAYNOW_UEN', '')
    merchant = getattr(settings, 'PAYNOW_MERCHANT_NAME', 'Cafeteria')[:25]
    if not uen:
        return ''

    amount_str = f'{float(amount):.2f}'

    # Tag 26: Merchant Account Information — PayNow
    merchant_account = (
        _emv_field('00', 'SG.PAYNOW') +
        _emv_field('01', '2') +              # Proxy Type: 2 = UEN
        _emv_field('02', uen) +              # Proxy value (UEN)
        _emv_field('03', '1')                # Editable amount: 1 = yes
    )

    # Tag 62: Additional Data — reference
    additional_data = _emv_field('01', reference[:25]) if reference else ''

    payload_without_crc = (
        _emv_field('00', '01') +              # Payload Format Indicator
        _emv_field('01', '12') +              # Point of Initiation (12 = dynamic)
        _emv_field('26', merchant_account) +  # Merchant account info (PayNow)
        _emv_field('52', '0000') +            # Merchant Category Code
        _emv_field('53', '702') +             # Currency: 702 = SGD
        _emv_field('54', amount_str) +        # Transaction amount
        _emv_field('58', 'SG') +              # Country
        _emv_field('59', merchant) +          # Merchant name
        _emv_field('60', 'Singapore') +       # Merchant city
        (_emv_field('62', additional_data) if additional_data else '') +
        '6304'                                # CRC tag + length prefix
    )
    crc = _crc16_ccitt(payload_without_crc)
    return payload_without_crc + crc

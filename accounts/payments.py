"""
Payment integration module.

Provides attempt_payment() which:
- In production with STRIPE_SECRET_KEY set: charges via Stripe
- In production with PAYNOW_UEN set: generates PayNow QR
- Otherwise: treats as 'cash' (success by default, for dev/kiosk)

Real Stripe/PayNow integration is a stub here — replace the TODO
sections with your provider's SDK calls when going live.
"""
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)


def attempt_payment(amount: Decimal, method: str, customer: str = '', metadata: dict = None):
    """
    Attempt a payment. Returns {'success': bool, 'message': str, 'transaction_id': str?}.

    method: 'cash', 'stripe', 'paynow', 'credits'
    """
    amount = Decimal(str(amount))
    metadata = metadata or {}

    if amount <= 0:
        return {'success': True, 'message': 'No payment required', 'transaction_id': ''}

    if method == 'cash':
        # Manual cash — trust the operator.
        return {'success': True, 'message': 'Cash payment accepted', 'transaction_id': f'CASH-{customer}'}

    if method == 'stripe':
        stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if not stripe_key:
            logger.warning('STRIPE_SECRET_KEY not set — falling back to cash mode')
            return {'success': True, 'message': 'Payment accepted (stub — Stripe not configured)', 'transaction_id': f'STUB-{customer}'}
        # TODO: real Stripe integration:
        # import stripe
        # stripe.api_key = stripe_key
        # intent = stripe.PaymentIntent.create(
        #     amount=int(amount * 100), currency='sgd', metadata=metadata,
        # )
        # return {'success': True, 'transaction_id': intent.id, 'client_secret': intent.client_secret}
        return {'success': True, 'message': 'Stripe payment processed (stub)', 'transaction_id': 'STRIPE-STUB'}

    if method == 'paynow':
        uen = getattr(settings, 'PAYNOW_UEN', '')
        if not uen:
            logger.warning('PAYNOW_UEN not set — falling back to cash mode')
            return {'success': True, 'message': 'Payment accepted (stub — PayNow not configured)', 'transaction_id': f'STUB-{customer}'}
        # TODO: generate SGQR PayNow QR code string (EMV format with UEN + amount).
        return {'success': True, 'message': 'PayNow QR generated (stub)', 'transaction_id': 'PAYNOW-STUB'}

    return {'success': False, 'message': f'Unknown payment method: {method}'}

"""
Reset every active staff user's credit balance to their monthly_credit allowance.

Run manually:
    python manage.py reset_credits

Or schedule via cron (if no Celery Beat):
    1 0 1 * *  cd /app && python manage.py reset_credits
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import StaffUser, CreditTransaction


class Command(BaseCommand):
    help = 'Reset all staff credit balances to their monthly allowance.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without changes')

    def handle(self, *args, **options):
        dry = options['dry_run']
        users = StaffUser.objects.filter(is_active=True).exclude(monthly_credit=0)
        total = 0
        with transaction.atomic():
            for u in users:
                old_bal = u.credit_balance
                new_bal = u.monthly_credit
                delta = Decimal(new_bal) - Decimal(old_bal)
                self.stdout.write(f'  {u.staff_id}: S${old_bal} → S${new_bal} (Δ {delta:+})')
                if not dry:
                    u.credit_balance = new_bal
                    u.save(update_fields=['credit_balance'])
                    CreditTransaction.objects.create(
                        user=u, type='allowance', amount=delta,
                        balance_after=new_bal,
                        notes=f'Monthly reset {timezone.localdate()}',
                    )
                total += 1
            if dry:
                self.stdout.write(self.style.WARNING(f'DRY RUN — {total} users would be reset'))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS(f'✓ Reset {total} users'))

"""
Custom management command: create_admin
Creates the initial superuser from environment variables non-interactively.

Usage (Railway start command or one-off):
    python manage.py create_admin

Required env vars:
    ADMIN_STAFF_ID    (default: ADMIN-001)
    ADMIN_EMAIL       (default: admin@example.com)
    ADMIN_PASSWORD    (required — no default for security)
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create superuser from environment variables (non-interactive)'

    def handle(self, *args, **options):
        User = get_user_model()
        staff_id = os.environ.get('ADMIN_STAFF_ID', 'ADMIN-001')
        email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        password = os.environ.get('ADMIN_PASSWORD', '')

        if not password:
            self.stdout.write(self.style.WARNING(
                'ADMIN_PASSWORD env var not set — skipping admin creation.'
            ))
            return

        if User.objects.filter(staff_id=staff_id).exists():
            self.stdout.write(self.style.SUCCESS(
                f'Admin "{staff_id}" already exists — skipping.'
            ))
            return

        User.objects.create_superuser(
            staff_id=staff_id,
            email=email,
            password=password,
            full_name='Administrator',
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superuser "{staff_id}" created successfully.'
        ))

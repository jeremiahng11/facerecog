"""
Create/ensure the initial administrative users from environment variables.
Idempotent — does nothing if the users already exist.

Two accounts are provisioned:

  ROOT — hidden super-user with total control. Invisible to regular admins
         in user lists. Use this for emergency access and system maintenance.
         Env vars: ROOT_ID, ROOT_EMAIL, ROOT_PASSWORD

  ADMIN — regular administrator account. Has full admin powers but is
         visible to other admins and can be managed.
         Env vars: ADMIN_STAFF_ID, ADMIN_EMAIL, ADMIN_PASSWORD

Usage:
    python manage.py create_admin
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create ROOT (hidden) and ADMIN (visible) users from env vars.'

    def handle(self, *args, **options):
        User = get_user_model()

        # ── ROOT (hidden super-user) ─────────────────────────────
        root_id = os.environ.get('ROOT_ID', 'ROOT')
        root_email = os.environ.get('ROOT_EMAIL', '')
        root_password = os.environ.get('ROOT_PASSWORD', '')

        if root_password and root_email:
            if User.objects.filter(staff_id=root_id).exists():
                self.stdout.write(self.style.SUCCESS(f'✓ Root "{root_id}" already exists — skipping'))
            else:
                root = User.objects.create_user(
                    staff_id=root_id,
                    email=root_email,
                    password=root_password,
                    full_name='Root',
                )
                root.is_staff = True
                root.is_superuser = True
                root.is_root = True
                root.role = 'admin'
                root.save()
                self.stdout.write(self.style.SUCCESS(f'✓ Root user "{root_id}" created (hidden from admin lists)'))
        else:
            self.stdout.write(self.style.WARNING('⚠ ROOT_EMAIL/ROOT_PASSWORD not set — skipping root creation'))

        # ── ADMIN (visible administrator) ────────────────────────
        admin_id = os.environ.get('ADMIN_STAFF_ID', 'ADMIN-001')
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', '')

        if not admin_password:
            self.stdout.write(self.style.WARNING('⚠ ADMIN_PASSWORD not set — skipping admin creation'))
            return

        if User.objects.filter(staff_id=admin_id).exists():
            self.stdout.write(self.style.SUCCESS(f'✓ Admin "{admin_id}" already exists — skipping'))
            return

        admin = User.objects.create_user(
            staff_id=admin_id,
            email=admin_email,
            password=admin_password,
            full_name='Administrator',
        )
        admin.is_staff = True
        admin.role = 'admin'
        admin.save()
        self.stdout.write(self.style.SUCCESS(f'✓ Admin "{admin_id}" created'))

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_staffuser_kiosk_pin'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='monthly_credit',
            field=models.DecimalField(decimal_places=2, default=50.00, help_text='Monthly cafeteria credit allowance in SGD', max_digits=8),
        ),
        migrations.AddField(
            model_name='staffuser',
            name='credit_balance',
            field=models.DecimalField(decimal_places=2, default=0.00, help_text='Current cafeteria credit balance in SGD', max_digits=8),
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('menu_type', models.CharField(choices=[('halal', 'Halal Kitchen'), ('non_halal', 'Non-Halal Kitchen'), ('cafe_bar', 'Cafe Bar')], max_length=16)),
                ('category', models.CharField(blank=True, help_text='e.g. Rice Meals, Noodles, Hot Drinks', max_length=50)),
                ('name', models.CharField(max_length=120)),
                ('description', models.CharField(blank=True, max_length=240)),
                ('staff_price', models.DecimalField(decimal_places=2, max_digits=6)),
                ('public_price', models.DecimalField(decimal_places=2, max_digits=6)),
                ('daily_quantity', models.PositiveIntegerField(default=0, help_text='Total daily stock (set at start of day)')),
                ('quantity_remaining', models.PositiveIntegerField(default=0)),
                ('low_stock_threshold', models.PositiveIntegerField(default=3)),
                ('is_available', models.BooleanField(default=True, help_text='Admin on/off toggle — overrides stock')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='menu/')),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('customizations', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['menu_type', 'display_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='OrderingHours',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('menu_type', models.CharField(choices=[('kitchen', 'Kitchen (Halal + Non-Halal)'), ('cafe_bar', 'Cafe Bar')], max_length=16)),
                ('label', models.CharField(blank=True, help_text='e.g. Lunch, Dinner, Morning', max_length=40)),
                ('opens_at', models.TimeField()),
                ('closes_at', models.TimeField()),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['menu_type', 'opens_at'],
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(help_text='e.g. H031, C019, N028, P042', max_length=10, unique=True)),
                ('is_public', models.BooleanField(default=False)),
                ('public_name', models.CharField(blank=True, help_text='For walk-in customers', max_length=60)),
                ('menu_type', models.CharField(choices=[('halal', 'Halal Kitchen'), ('non_halal', 'Non-Halal Kitchen'), ('cafe_bar', 'Cafe Bar')], max_length=16)),
                ('status', models.CharField(choices=[('pending', 'Pending Payment'), ('confirmed', 'Confirmed'), ('preparing', 'Preparing'), ('ready', 'Ready for Collection'), ('collected', 'Collected'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded')], default='pending', max_length=16)),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('credits_applied', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('balance_due', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('payment_method', models.CharField(blank=True, choices=[('credits', 'Staff Credits'), ('stripe', 'Stripe Card'), ('paynow', 'PayNow QR'), ('cash', 'Cash'), ('mixed', 'Credits + Card/PayNow')], max_length=12)),
                ('qr_token', models.CharField(blank=True, max_length=200, unique=True)),
                ('qr_used', models.BooleanField(default=False)),
                ('qr_used_at', models.DateTimeField(blank=True, null=True)),
                ('collection_time_minutes', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('ready_at', models.DateTimeField(blank=True, null=True)),
                ('collected_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_reason', models.CharField(blank=True, max_length=200)),
                ('customer', models.ForeignKey(blank=True, help_text='Null for public walk-in', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name_snapshot', models.CharField(help_text='Name at time of order', max_length=120)),
                ('price_snapshot', models.DecimalField(decimal_places=2, max_digits=6)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('customizations', models.JSONField(blank=True, default=dict)),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('menu_item', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.menuitem')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='accounts.order')),
            ],
        ),
        migrations.CreateModel(
            name='CreditTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('allowance', 'Monthly Allowance'), ('order', 'Order Debit'), ('refund', 'Refund Credit'), ('admin_adjust', 'Admin Adjustment')], max_length=16)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Positive=credit, negative=debit', max_digits=8)),
                ('balance_after', models.DecimalField(decimal_places=2, max_digits=8)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('related_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.order')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credit_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='QRScanLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scanner_device', models.CharField(blank=True, help_text='e.g. halal_kitchen, cafe_bar', max_length=50)),
                ('result', models.CharField(choices=[('valid', 'Valid'), ('wrong_counter', 'Wrong Counter'), ('duplicate', 'Duplicate (already used)'), ('invalid', 'Invalid (tampered or unknown)'), ('not_ready', 'Not Ready')], max_length=16)),
                ('token_preview', models.CharField(blank=True, help_text='First 40 chars of scanned token', max_length=40)),
                ('scanned_at', models.DateTimeField(auto_now_add=True)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.order')),
                ('scanned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='qr_scans', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-scanned_at'],
            },
        ),
    ]

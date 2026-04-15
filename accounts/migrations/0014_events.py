from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_local_international_labels_and_vegetarian'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staffuser',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Staff (ordering only)'),
                    ('kitchen', 'Kitchen Counter'),
                    ('cafe_bar', 'Cafe Bar Counter'),
                    ('kitchen_admin', 'Kitchen Admin (menus + events)'),
                    ('admin', 'Administrator'),
                ],
                help_text='Workstation role — controls access to counter views',
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name='EventMenu',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. Executive Lunch Package, Asian Buffet', max_length=120)),
                ('description', models.TextField(blank=True)),
                ('price_per_pax', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('min_pax', models.PositiveIntegerField(default=10)),
                ('max_pax', models.PositiveIntegerField(default=200)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='event_menus/')),
                ('is_available', models.BooleanField(default=True)),
                ('is_vegetarian', models.BooleanField(default=False, help_text='Entire package is vegetarian')),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_event_menus',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['display_order', 'name']},
        ),
        migrations.CreateModel(
            name='EventMenuItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(
                    choices=[
                        ('appetizer', 'Appetizer'),
                        ('main', 'Main Course'),
                        ('side', 'Side Dish'),
                        ('drink', 'Drink'),
                        ('dessert', 'Dessert'),
                        ('other', 'Other'),
                    ],
                    max_length=20,
                )),
                ('name', models.CharField(max_length=120)),
                ('description', models.CharField(blank=True, max_length=240)),
                ('is_vegetarian', models.BooleanField(default=False)),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('event_menu', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='components',
                    to='accounts.eventmenu',
                )),
            ],
            options={'ordering': ['event_menu', 'category', 'display_order']},
        ),
        migrations.CreateModel(
            name='EventBooking',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(
                    choices=[
                        ('team_bonding', 'Team Bonding'),
                        ('meeting', 'Meeting'),
                        ('discussion', 'Discussion'),
                        ('vip', 'VIP Event'),
                        ('other', 'Other'),
                    ],
                    max_length=20,
                )),
                ('pax', models.PositiveIntegerField()),
                ('event_date', models.DateField()),
                ('event_time', models.TimeField()),
                ('venue', models.CharField(max_length=200)),
                ('notes', models.TextField(blank=True)),
                ('title', models.CharField(blank=True, help_text='Optional event title (e.g. Q3 Offsite)', max_length=160)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending Approval'),
                        ('approved', 'Approved'),
                        ('rejected', 'Rejected'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('booked_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='event_bookings',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('event_menu', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='bookings',
                    to='accounts.eventmenu',
                )),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_event_bookings',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-event_date', '-event_time']},
        ),
    ]

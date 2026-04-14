import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_cafeteria_system'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_token',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_received_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payments_received',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='is_mixed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='menu_type_snapshot',
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='collected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='menu_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('halal', 'Halal Kitchen'),
                    ('non_halal', 'Non-Halal Kitchen'),
                    ('cafe_bar', 'Cafe Bar'),
                    ('mixed', 'Mixed'),
                ],
                max_length=16,
            ),
        ),
    ]

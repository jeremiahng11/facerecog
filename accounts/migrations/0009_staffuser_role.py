from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_mixed_orders_and_payment_qr'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Staff (ordering only)'),
                    ('kitchen', 'Kitchen Counter'),
                    ('cafe_bar', 'Cafe Bar Counter'),
                    ('admin', 'Administrator'),
                ],
                help_text='Workstation role — controls access to counter views',
                max_length=16,
            ),
        ),
    ]

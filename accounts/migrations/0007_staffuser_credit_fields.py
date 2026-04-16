from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_staffuser_kiosk_pin'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='monthly_credit',
            field=models.DecimalField(
                decimal_places=2, default=50.00, max_digits=8,
                help_text='Monthly cafeteria credit allowance',
            ),
        ),
        migrations.AddField(
            model_name='staffuser',
            name='credit_balance',
            field=models.DecimalField(
                decimal_places=2, default=0.00, max_digits=8,
                help_text='Current cafeteria credit balance',
            ),
        ),
    ]

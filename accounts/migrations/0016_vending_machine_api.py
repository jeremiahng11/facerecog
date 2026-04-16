from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_kioskconfig_credit_working_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='credittransaction',
            name='status',
            field=models.CharField(
                choices=[('success', 'Success'), ('failed', 'Failed')],
                default='success',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='credittransaction',
            name='machine_id',
            field=models.CharField(
                blank=True, default='', max_length=50,
                help_text='Vending machine identifier',
            ),
        ),
        migrations.AlterField(
            model_name='credittransaction',
            name='type',
            field=models.CharField(
                choices=[
                    ('allowance', 'Monthly Allowance'),
                    ('order', 'Order Debit'),
                    ('refund', 'Refund Credit'),
                    ('admin_adjust', 'Admin Adjustment'),
                    ('vending', 'Vending Machine'),
                ],
                max_length=16,
            ),
        ),
    ]

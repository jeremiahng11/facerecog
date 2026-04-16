from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_vending_machine_api'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='staff_type',
            field=models.CharField(
                choices=[('permanent', 'Permanent'), ('temp', 'Temp Staff'), ('intern', 'Intern')],
                default='permanent',
                help_text='Temp and Intern accounts are auto-disabled after contract end date',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='staffuser',
            name='contract_end_date',
            field=models.DateField(
                blank=True, null=True,
                help_text='Last working day — account auto-disabled after this date',
            ),
        ),
    ]

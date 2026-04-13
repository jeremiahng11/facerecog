from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_queueticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='kiosk_pin',
            field=models.CharField(
                blank=True,
                help_text='4-6 digit PIN for kiosk queue login (set in Profile)',
                max_length=6,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='kioskconfig',
            name='credit_working_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Working days per month (used for prorating new staff credit).',
            ),
        ),
    ]

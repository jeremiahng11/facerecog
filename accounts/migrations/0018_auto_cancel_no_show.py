import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_staffuser_temp_intern'),
    ]

    operations = [
        migrations.AddField(
            model_name='kioskconfig',
            name='kitchen_cutoff_time',
            field=models.TimeField(
                default=datetime.time(17, 1),
                help_text='Kitchen (Local + International) daily cutoff — uncollected orders auto-cancel after this time',
            ),
        ),
        migrations.AddField(
            model_name='kioskconfig',
            name='cafe_bar_cutoff_time',
            field=models.TimeField(
                default=datetime.time(20, 1),
                help_text='Cafe Bar daily cutoff — uncollected orders auto-cancel after this time',
            ),
        ),
        migrations.AddField(
            model_name='kioskconfig',
            name='no_show_minutes',
            field=models.PositiveIntegerField(
                default=20,
                help_text='Minutes after order is ready before it appears as No Show at the counter',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Payment'),
                    ('confirmed', 'Confirmed'),
                    ('preparing', 'Preparing'),
                    ('ready', 'Ready for Collection'),
                    ('collected', 'Collected'),
                    ('cancelled', 'Cancelled'),
                    ('refunded', 'Refunded'),
                    ('no_show', 'No Show'),
                ],
                default='pending',
                max_length=16,
            ),
        ),
    ]

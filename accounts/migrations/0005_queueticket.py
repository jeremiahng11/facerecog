import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_adminactionlog'),
    ]

    operations = [
        migrations.CreateModel(
            name='QueueTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(help_text='Queue number for the day (auto-incremented)')),
                ('status', models.CharField(choices=[('waiting', 'Waiting'), ('serving', 'Now Serving'), ('served', 'Served'), ('cancelled', 'Cancelled')], default='waiting', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('served_at', models.DateTimeField(blank=True, null=True)),
                ('date', models.DateField(default=django.utils.timezone.now, help_text='Queue date (resets daily)')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='queue_tickets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['date', 'number'],
                'unique_together': {('date', 'number')},
            },
        ),
    ]

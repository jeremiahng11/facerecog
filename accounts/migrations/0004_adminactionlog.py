import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_faceloginlog_device'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Created user'), ('edit', 'Edited user'), ('delete', 'Deleted user'), ('reencode', 'Re-encoded face')], max_length=20)),
                ('target_staff_id', models.CharField(max_length=50)),
                ('target_name', models.CharField(blank=True, max_length=150)),
                ('details', models.CharField(blank=True, max_length=300)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('admin_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
    ]

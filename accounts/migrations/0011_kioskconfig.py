from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_staffuser_is_root'),
    ]

    operations = [
        migrations.CreateModel(
            name='KioskConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idle_landing_seconds', models.PositiveIntegerField(
                    default=15,
                    help_text='Idle screen countdown before kiosk resets.',
                )),
                ('idle_session_seconds', models.PositiveIntegerField(
                    default=30,
                    help_text='Auto-logout after this many seconds of inactivity on any post-login kiosk screen.',
                )),
                ('post_print_seconds', models.PositiveIntegerField(
                    default=5,
                    help_text='Auto-return to idle screen this many seconds after Print is clicked.',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Kiosk Configuration',
            },
        ),
    ]

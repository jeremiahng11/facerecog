from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_staffuser_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffuser',
            name='is_root',
            field=models.BooleanField(
                default=False,
                help_text='Hidden root user — invisible to regular admins',
            ),
        ),
    ]

from django.db import migrations, models


def enable_face_for_all_users(apps, schema_editor):
    """Enable Face ID login for every existing user."""
    StaffUser = apps.get_model('accounts', 'StaffUser')
    StaffUser.objects.all().update(face_enabled=True)


def disable_face_for_all_users(apps, schema_editor):
    """Reverse: restore previous default of disabled."""
    StaffUser = apps.get_model('accounts', 'StaffUser')
    StaffUser.objects.all().update(face_enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staffuser',
            name='face_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Allow this user to login via Face ID',
            ),
        ),
        migrations.RunPython(
            enable_face_for_all_users,
            disable_face_for_all_users,
        ),
    ]

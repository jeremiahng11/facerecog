from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaffUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False)),
                ('staff_id', models.CharField(max_length=50, unique=True)),
                ('email', models.EmailField(unique=True)),
                ('full_name', models.CharField(max_length=150)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('profile_picture', models.ImageField(blank=True, null=True, upload_to='profile_pics/')),
                ('face_photo', models.ImageField(blank=True, help_text='Primary face photo used for recognition', null=True, upload_to='face_photos/')),
                ('face_encoding', models.TextField(blank=True, help_text='JSON-encoded face encoding vector', null=True)),
                ('face_registered', models.BooleanField(default=False)),
                ('face_enabled', models.BooleanField(default=False, help_text='Allow this user to login via Face ID')),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_face_login', models.DateTimeField(blank=True, null=True)),
                ('groups', models.ManyToManyField(blank=True, related_name='staffuser_set', to='auth.group')),
                ('user_permissions', models.ManyToManyField(blank=True, related_name='staffuser_set', to='auth.permission')),
            ],
            options={
                'verbose_name': 'Staff User',
                'verbose_name_plural': 'Staff Users',
            },
        ),
        migrations.CreateModel(
            name='FaceLoginLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('success', models.BooleanField(default=False)),
                ('confidence', models.FloatField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='face_login_logs', to='accounts.staffuser')),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
    ]

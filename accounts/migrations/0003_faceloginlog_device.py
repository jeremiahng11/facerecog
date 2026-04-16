from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_enable_face_recognition_by_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='faceloginlog',
            name='device',
            field=models.CharField(
                blank=True,
                help_text='Parsed device/browser info from User-Agent',
                max_length=120,
            ),
        ),
    ]

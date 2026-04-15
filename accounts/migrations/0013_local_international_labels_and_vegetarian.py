from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_orderinghours_weekdays_and_holiday'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='is_vegetarian',
            field=models.BooleanField(default=False, help_text='Mark this dish as vegetarian'),
        ),
        migrations.AlterField(
            model_name='menuitem',
            name='menu_type',
            field=models.CharField(
                choices=[('halal', 'Local'), ('non_halal', 'International'), ('cafe_bar', 'Cafe Bar')],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='orderinghours',
            name='menu_type',
            field=models.CharField(
                choices=[('kitchen', 'Kitchen (Local + International)'), ('cafe_bar', 'Cafe Bar')],
                max_length=16,
            ),
        ),
    ]

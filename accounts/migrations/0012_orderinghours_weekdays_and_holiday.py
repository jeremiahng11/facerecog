from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_kioskconfig'),
    ]

    operations = [
        migrations.AddField(model_name='orderinghours', name='mon', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='tue', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='wed', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='thu', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='fri', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='sat', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='orderinghours', name='sun', field=models.BooleanField(default=True)),
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('label', models.CharField(help_text='e.g. Christmas Day, Stock-take', max_length=100)),
                ('scope', models.CharField(
                    choices=[('all', 'Everything closed'), ('kitchen', 'Kitchen only'), ('cafe_bar', 'Cafe Bar only')],
                    default='all', max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['date']},
        ),
    ]

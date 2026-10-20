from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0055_alter_group_verbose_names'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_known_boot_time', models.DateTimeField(blank=True, null=True, verbose_name='Poslední známý čas bootu RPi')),
            ],
            options={
                'verbose_name': 'Stav systému',
                'verbose_name_plural': 'Stav systému',
            },
        ),
    ]

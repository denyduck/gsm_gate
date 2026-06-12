from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0022_automationrule_users'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceObject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Název objektu')),
                ('object_type', models.CharField(choices=[('FREEZER', 'Mrazák'), ('ALARM', 'Alarm'), ('SENSOR', 'Senzor'), ('GATEWAY', 'Brána'), ('OTHER', 'Jiný objekt')], default='OTHER', max_length=20, verbose_name='Typ objektu')),
                ('icon', models.CharField(choices=[('snow', 'Mrazák'), ('bell', 'Alarm'), ('thermometer-half', 'Teplota'), ('shield-exclamation', 'Bezpečnost'), ('wifi', 'Síť'), ('hdd-network', 'Zařízení'), ('cpu', 'Řídicí jednotka'), ('lightning-charge', 'Energie')], default='hdd-network', max_length=40, verbose_name='Ikona')),
                ('active', models.BooleanField(default=True, verbose_name='Aktivní')),
                ('status_flag', models.CharField(choices=[('OK', 'OK'), ('WARN', 'Varování'), ('ALERT', 'Poplach'), ('OFFLINE', 'Offline')], default='OK', max_length=10, verbose_name='Příznak stavu')),
                ('status_label', models.CharField(blank=True, max_length=120, verbose_name='Vlastní popisek stavu')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='Popis')),
                ('specification', models.TextField(blank=True, verbose_name='Specifikace')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Vytvořeno')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Upraveno')),
                ('owner', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='device_objects', to=settings.AUTH_USER_MODEL, verbose_name='Vlastník')),
            ],
            options={
                'verbose_name': 'Objekt zařízení',
                'verbose_name_plural': 'Objekty zařízení',
                'ordering': ['name', 'id'],
            },
        ),
    ]

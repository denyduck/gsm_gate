from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0023_deviceobject'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceObjectApiCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=128, unique=True, verbose_name='API token')),
                ('active', models.BooleanField(default=True, verbose_name='Aktivní')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Vytvořeno')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Upraveno')),
                ('last_used_at', models.DateTimeField(blank=True, null=True, verbose_name='Naposledy použito')),
                ('device_object', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='api_credential', to='dashboard.deviceobject', verbose_name='Objekt zařízení')),
            ],
            options={
                'verbose_name': 'API klíč objektu',
                'verbose_name_plural': 'API klíče objektů',
            },
        ),
    ]

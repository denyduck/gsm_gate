from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0035_alter_gatewaysettings_last_signal_quality'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BlockedNumber',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=30, verbose_name='Telefonní číslo')),
                ('reason', models.CharField(blank=True, max_length=255, verbose_name='Důvod')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Vytvořeno')),
                ('expires_at', models.DateTimeField(blank=True, help_text='Prázdné = trvalá blokace.', null=True, verbose_name='Platí do')),
                ('owner', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='blocked_numbers', to=settings.AUTH_USER_MODEL, verbose_name='Vlastník')),
            ],
            options={
                'verbose_name': 'Blokované číslo',
                'verbose_name_plural': 'Blokovaná čísla',
                'ordering': ['-created_at'],
                'unique_together': {('owner', 'number')},
            },
        ),
    ]

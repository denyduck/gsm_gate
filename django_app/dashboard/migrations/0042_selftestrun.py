from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0041_gatewaysettings_cleanup'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SelfTestRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Spuštěno')),
                (
                    'overall_status',
                    models.CharField(
                        choices=[('OK', 'OK'), ('WARN', 'Varování'), ('ERROR', 'Chyba')],
                        max_length=10,
                        verbose_name='Celkový výsledek',
                    ),
                ),
                ('results', models.JSONField(default=list, verbose_name='Výsledky kontrol')),
                (
                    'owner',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='self_test_runs',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Spustil',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Sebediagnostika',
                'verbose_name_plural': 'Sebediagnostiky',
                'ordering': ['-created_at'],
            },
        ),
    ]

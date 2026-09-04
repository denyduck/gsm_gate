from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0044_automationrule_first_contact_notice'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SignalReading',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'quality',
                    models.PositiveIntegerField(
                        blank=True,
                        help_text='Prázdné = modem nebyl v tomto cyklu dostupný (výpadek).',
                        null=True,
                        verbose_name='Síla signálu (%)',
                    ),
                ),
                ('recorded_at', models.DateTimeField(auto_now_add=True, verbose_name='Zaznamenáno')),
                (
                    'owner',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='signal_readings',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Vlastník',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Záznam síly signálu',
                'verbose_name_plural': 'Záznamy síly signálu',
                'ordering': ['-recorded_at'],
            },
        ),
    ]

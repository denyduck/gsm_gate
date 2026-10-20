from django.db import migrations, models


class Migration(migrations.Migration):
    """Jen rozšíření choices (žádná změna DB schématu) - bez tohohle by
    nešlo vytvořit pravidlo reagující na SYSTEM události (restart RPi,
    přihlášení admina, útok na přihlášení) - viz services/rules_engine.py
    fire_system_health_event()."""

    dependencies = [
        ('dashboard', '0056_systemstate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationrule',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('SMS', 'Příchozí SMS'),
                    ('API', 'Příchozí API událost'),
                    ('SMS_API', 'SMS i API událost'),
                    ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
                    ('SYSTEM', 'Systémová/provozní událost brány (restart, přihlášení admina, útok na přihlášení)'),
                ],
                default='SMS_API',
                max_length=20,
                verbose_name='Typ události',
            ),
        ),
    ]

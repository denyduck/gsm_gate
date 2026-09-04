from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0047_deviceobject_users'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='first_contact_timing',
            field=models.CharField(
                choices=[
                    ('ON_TRIGGER', 'Až se pravidlo poprvé spustí na dané číslo'),
                    ('ON_SAVE', 'Hned po vytvoření/uložení pravidla'),
                ],
                default='ON_TRIGGER',
                help_text='"Hned po uložení" pošle SMS ihned všem aktuálním cílovým číslům, ne až při skutečné události.',
                max_length=20,
                verbose_name='Kdy odeslat informační SMS',
            ),
        ),
        migrations.AlterField(
            model_name='incomingeventlog',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('SMS', 'Příchozí SMS'),
                    ('API', 'Příchozí API událost'),
                    ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
                    ('SYSTEM', 'Systémová událost (např. uložení pravidla)'),
                ],
                max_length=20,
                verbose_name='Typ události',
            ),
        ),
    ]

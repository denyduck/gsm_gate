from django.db import migrations, models


class Migration(migrations.Migration):
    """first_contact_timing = blank=True (jen stav formuláře, žádná změna
    DB schématu) - viz help_text u pole a docs/modem-diagnostika.md.
    Dřív appka při vypnutém "Odeslat informační SMS..." vracela
    "Toto pole je třeba vyplnit", protože JS pole schová A zakáže, takže se
    vůbec neodeslalo, zatímco model ho bral jako povinné."""

    dependencies = [
        ('dashboard', '0051_gatewaysettings_delivery_reports_default_off'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationrule',
            name='first_contact_timing',
            field=models.CharField(
                blank=True,
                choices=[('ON_TRIGGER', 'Až se pravidlo poprvé spustí na dané číslo'), ('ON_SAVE', 'Hned po vytvoření/uložení pravidla')],
                default='ON_TRIGGER',
                help_text=(
                    '"Hned po uložení" pošle SMS ihned všem aktuálním cílovým číslům, ne až při skutečné '
                    'události. Nepovinné - relevantní jen když je zapnuté "Odeslat informační SMS při prvním '
                    'kontaktu" výše; JS formulář toto pole při vypnutém přepínači schová a zakáže (nejde pak '
                    'odeslat), takže bez "blank=True" by server validaci odmítl jako chybějící povinné pole '
                    '(reálně pozorováno).'
                ),
                max_length=20,
                verbose_name='Kdy odeslat informační SMS',
            ),
        ),
    ]

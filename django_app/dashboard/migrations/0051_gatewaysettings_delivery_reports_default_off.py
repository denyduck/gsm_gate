from django.db import migrations, models


def disable_existing_delivery_reports(apps, schema_editor):
    """Reálný incident 2026-09-11: s Teltonika Calyx (generický ModemManager
    plugin) appka doručenku umí vykázat jako běžnou novou příchozí SMS od
    příjemce, což v kombinaci s pravidlem "Jakékoliv číslo -> Předat na
    číslo" na stejné číslo vedlo k nekonečné smyčce odchozích SMS - viz
    docs/modem-diagnostika.md. Existující zapnuté nastavení vypneme, ať
    tahle past nezůstane aktivní jen proto, že řádek vznikl před opravou."""
    GatewaySettings = apps.get_model('dashboard', 'GatewaySettings')
    GatewaySettings.objects.filter(delivery_reports=True).update(delivery_reports=False)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0050_gatewaysettings_help_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gatewaysettings',
            name='delivery_reports',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Při odeslání SMS požádá síť o potvrzení doručení příjemci. POZOR: s Teltonika Calyx '
                    '(generický ModemManager plugin) appka doručenku umí vykázat jako běžnou novou příchozí '
                    'SMS od příjemce - v kombinaci s pravidlem "Jakékoliv číslo → Předat na číslo" na stejné '
                    'číslo to vede k nekonečné smyčce odchozích SMS (reálný incident 2026-09-11, viz '
                    'docs/modem-diagnostika.md). Výchozí hodnota je proto vypnuto.'
                ),
                verbose_name='Vyžadovat doručenky',
            ),
        ),
        migrations.RunPython(disable_existing_delivery_reports, migrations.RunPython.noop),
    ]

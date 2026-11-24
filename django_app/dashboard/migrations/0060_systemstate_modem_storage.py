from django.db import migrations, models


class Migration(migrations.Migration):
    """Sledování obsazenosti paměti SMS v modemu a pozastavení odesílání -
    incident 2026-11 (zbytky odchozích SMS zaplnily paměť modemu, brána
    přestala přijímat SMS), viz docs/modem-diagnostika.md."""

    dependencies = [
        ('dashboard', '0059_automationrule_message_flag_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_used',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='SMS v paměti modemu'),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_capacity',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Kapacita paměti SMS'),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_capacity_source',
            field=models.CharField(
                blank=True, max_length=10, verbose_name='Zdroj kapacity',
                help_text='AT = skutečná hodnota z modemu (AT+CPMS?), CONFIG = odhad z GSM_MODEM_SMS_CAPACITY.',
            ),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_storage',
            field=models.CharField(blank=True, max_length=10, verbose_name='Úložiště SMS'),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_states',
            field=models.JSONField(blank=True, default=dict, verbose_name='SMS v modemu podle stavu'),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_delete_failures',
            field=models.PositiveIntegerField(
                default=0, verbose_name='Neúspěšná mazání',
                help_text='Kolik SMS se v posledním cyklu nepodařilo z modemu smazat.',
            ),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='modem_sms_checked_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Paměť SMS naposledy zjištěna'),
        ),
        migrations.AddField(
            model_name='systemstate',
            name='sms_sending_paused_reason',
            field=models.CharField(
                blank=True, max_length=255, verbose_name='Důvod pozastavení odesílání SMS',
                help_text='Vyplněné, pokud worker v posledním cyklu SMS neodesílal (plná paměť, opakovaná selhání).',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    """Číslo brány (ochrana proti smyčce), opakování neodeslaných SMS a
    zrušení čekajících SMS - viz services/sms_dispatch.py."""

    dependencies = [
        ('dashboard', '0060_systemstate_modem_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='gatewaysettings',
            name='own_number',
            field=models.CharField(
                blank=True, max_length=30, verbose_name='Číslo brány (SIM)',
                help_text=(
                    'Telefonní číslo SIM karty v bráně. Brána na něj nikdy neodešle SMS a příchozí SMS z něj '
                    'ignoruje (ochrana proti smyčce). Při výměně SIM karty ho uprav.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='outgoingaction',
            name='attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Počet pokusů'),
        ),
        migrations.AddField(
            model_name='outgoingaction',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Další pokus'),
        ),
        migrations.AlterField(
            model_name='outgoingaction',
            name='status',
            field=models.CharField(
                choices=[('PENDING', 'Čeká'), ('SENT', 'Odesláno'), ('FAILED', 'Chyba'), ('CANCELLED', 'Zrušeno')],
                default='PENDING', max_length=10, verbose_name='Stav',
            ),
        ),
    ]

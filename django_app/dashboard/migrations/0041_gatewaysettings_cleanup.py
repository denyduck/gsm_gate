from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0040_automationrule_is_protected'),
    ]

    operations = [
        migrations.RemoveField(model_name='gatewaysettings', name='serial_port'),
        migrations.RemoveField(model_name='gatewaysettings', name='baud_rate'),
        migrations.RemoveField(model_name='gatewaysettings', name='apn'),
        migrations.RemoveField(model_name='gatewaysettings', name='network_mode'),
        migrations.RemoveField(model_name='gatewaysettings', name='sms_storage'),
        migrations.RemoveField(model_name='gatewaysettings', name='auto_start_gateway'),
        migrations.RemoveField(model_name='gatewaysettings', name='heartbeat_interval_sec'),
        migrations.AlterField(
            model_name='gatewaysettings',
            name='pin_code',
            field=models.CharField(
                blank=True,
                help_text='Vyplň, jen pokud SIM karta vyžaduje PIN. Worker ho použije k odemčení modemu.',
                max_length=16,
                verbose_name='PIN SIM',
            ),
        ),
        migrations.AlterField(
            model_name='gatewaysettings',
            name='delivery_reports',
            field=models.BooleanField(
                default=True,
                help_text='Při odeslání SMS požádá síť o potvrzení doručení příjemci.',
                verbose_name='Vyžadovat doručenky',
            ),
        ),
        migrations.AlterField(
            model_name='gatewaysettings',
            name='webhook_url',
            field=models.URLField(blank=True, verbose_name='Webhook URL (Teams)'),
        ),
    ]

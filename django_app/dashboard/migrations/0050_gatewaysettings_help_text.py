from django.db import migrations, models


class Migration(migrations.Migration):
    """Jen help_text (zobrazí se v UI/adminu) - žádná změna schématu DB."""

    dependencies = [
        ('dashboard', '0049_automationrule_include_source_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gatewaysettings',
            name='allow_incoming_sms',
            field=models.BooleanField(
                default=True,
                help_text='Vypnutím se pro tebe přestanou vyhodnocovat pravidla na příchozí SMS – worker zprávy dál čte a maže z modemu, jen je nikomu nepředá. Nemá vliv na API události.',
                verbose_name='Povolit příchozí SMS',
            ),
        ),
        migrations.AlterField(
            model_name='gatewaysettings',
            name='webhook_url',
            field=models.URLField(
                blank=True,
                help_text='Incoming Webhook URL z Microsoft Teams kanálu, kam mají chodit notifikace přes kanál "Teams" v pravidlech. Bez vyplnění tahle akce selže.',
                verbose_name='Webhook URL (Teams)',
            ),
        ),
    ]

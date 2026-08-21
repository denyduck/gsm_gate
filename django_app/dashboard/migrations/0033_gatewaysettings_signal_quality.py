# Generated manually to add signal quality tracking to GatewaySettings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0032_outgoingaction_processing_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='gatewaysettings',
            name='last_signal_quality',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Poslední síla signálu (CSQ)'),
        ),
        migrations.AddField(
            model_name='gatewaysettings',
            name='last_signal_checked_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Signál naposledy zjištěn'),
        ),
    ]

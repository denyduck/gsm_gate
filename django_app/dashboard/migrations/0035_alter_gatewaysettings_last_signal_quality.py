# Generated manually - relabel last_signal_quality as percentage (ModemManager), not CSQ

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0034_alter_automationrule_event_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gatewaysettings',
            name='last_signal_quality',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Poslední síla signálu (%)'),
        ),
    ]

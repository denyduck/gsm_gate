from django.db import migrations, models


def protect_default_security_rule(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.filter(
        name='Výchozí: Upozornění na bezpečnostní blokaci',
    ).update(is_protected=True)


def unprotect_default_security_rule(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.filter(
        name='Výchozí: Upozornění na bezpečnostní blokaci',
    ).update(is_protected=False)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0039_security_event_type_and_default_rule'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='is_protected',
            field=models.BooleanField(
                default=False,
                help_text='Nejde smazat ani upravit v appce – jen zapnout/vypnout a nastavit přes Django Admin.',
                verbose_name='Chráněné systémové pravidlo',
            ),
        ),
        migrations.RunPython(protect_default_security_rule, unprotect_default_security_rule),
    ]

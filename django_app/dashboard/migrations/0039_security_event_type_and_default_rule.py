from django.db import migrations, models


def seed_default_security_rule(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')

    for user in User.objects.filter(is_active=True):
        AutomationRule.objects.get_or_create(
            owner=user,
            name='Výchozí: Upozornění na bezpečnostní blokaci',
            defaults={
                'description': (
                    'Reaguje na automatické nebo ruční zablokování čísla '
                    '(ochrana proti zahlcení SMS/API). Vypnuto, dokud si '
                    'nenastavíš cílová čísla/skupiny nebo e-mail/Teams kanál.'
                ),
                'active': False,
                'priority': 10,
                'event_type': 'SECURITY',
                'match_type': 'ANY',
                'action': 'NOTIFY_NUM',
                'include_original_message': True,
                'custom_message': 'Bezpečnostní upozornění: brána zablokovala podezřelé číslo.',
                'stop_processing': True,
            },
        )


def unseed_default_security_rule(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.filter(name='Výchozí: Upozornění na bezpečnostní blokaci').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0038_securityrule'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationrule',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('SMS', 'Příchozí SMS'),
                    ('API', 'Příchozí API událost'),
                    ('SMS_API', 'SMS i API událost'),
                    ('ANY', 'SMS i API událost'),
                    ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
                ],
                default='ANY',
                max_length=20,
                verbose_name='Typ události',
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
                ],
                max_length=20,
                verbose_name='Typ události',
            ),
        ),
        migrations.RunPython(seed_default_security_rule, unseed_default_security_rule),
    ]

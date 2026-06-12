from django.db import migrations, models


def split_notify_actions_forward(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')

    for rule in AutomationRule.objects.filter(action='NOTIFY').iterator():
        has_target_numbers = rule.target_numbers.exists()
        has_target_groups = rule.target_groups.exists()

        if has_target_groups and not has_target_numbers:
            rule.action = 'NOTIFY_GRP'
        else:
            rule.action = 'NOTIFY_NUM'

        rule.save(update_fields=['action'])


def split_notify_actions_backward(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.filter(action__in=['NOTIFY_NUM', 'NOTIFY_GRP']).update(action='NOTIFY')


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0014_seed_default_gateway_data'),
    ]

    operations = [
        migrations.RunPython(split_notify_actions_forward, split_notify_actions_backward),
        migrations.AlterField(
            model_name='automationrule',
            name='action',
            field=models.CharField(
                choices=[
                    ('IGNORE', 'Ignorovat'),
                    ('NOTIFY_NUM', 'Poslat informaci na cílová čísla'),
                    ('NOTIFY_GRP', 'Poslat informaci na cílové skupiny'),
                    ('FORWARD', 'Předat informaci na jedno číslo'),
                ],
                default='IGNORE',
                max_length=10,
                verbose_name='Reakce',
            ),
        ),
    ]

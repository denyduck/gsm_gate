from django.db import migrations, models


def merge_any_into_sms_api(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.filter(event_type='ANY').update(event_type='SMS_API')


def split_sms_api_back_to_any(apps, schema_editor):
    # Nevratné beze ztráty informace (SMS_API a ANY se chovaly identicky -
    # nešlo by poznat, které řádky byly původně ANY) - no-op při rollbacku.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0045_signalreading'),
    ]

    operations = [
        migrations.RunPython(merge_any_into_sms_api, split_sms_api_back_to_any),
        migrations.AlterField(
            model_name='automationrule',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('SMS', 'Příchozí SMS'),
                    ('API', 'Příchozí API událost'),
                    ('SMS_API', 'SMS i API událost'),
                    ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
                ],
                default='SMS_API',
                max_length=20,
                verbose_name='Typ události',
            ),
        ),
    ]

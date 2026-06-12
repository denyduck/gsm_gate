from django.db import migrations, models


def copy_source_group_to_source_groups(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')

    for rule in AutomationRule.objects.exclude(source_group__isnull=True).iterator():
        rule.source_groups.add(rule.source_group)


def copy_source_groups_to_source_group(apps, schema_editor):
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')

    for rule in AutomationRule.objects.all().iterator():
        first_group = rule.source_groups.first()
        rule.source_group = first_group
        rule.save(update_fields=['source_group'])


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0017_alter_outgoingaction_action_type_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='source_groups',
            field=models.ManyToManyField(blank=True, related_name='source_automation_rules_multi', to='dashboard.group', verbose_name='Zdrojové skupiny'),
        ),
        migrations.RunPython(copy_source_group_to_source_groups, copy_source_groups_to_source_group),
    ]

from django.db import migrations


def seed_default_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    readonly_group, _ = Group.objects.get_or_create(name='Jen čtení')
    operator_group, _ = Group.objects.get_or_create(name='Operátor')

    readonly_codenames = [
        'view_phonenumber',
        'view_group',
        'view_gatewaysettings',
        'view_rule',
        'view_automationrule',
        'view_incomingeventlog',
        'view_outgoingaction',
    ]

    operator_codenames = [
        'view_phonenumber',
        'add_phonenumber',
        'change_phonenumber',
        'delete_phonenumber',
        'view_group',
        'add_group',
        'change_group',
        'delete_group',
        'view_gatewaysettings',
        'view_rule',
        'view_automationrule',
        'view_incomingeventlog',
        'view_outgoingaction',
    ]

    readonly_permissions = Permission.objects.filter(
        content_type__app_label='dashboard',
        codename__in=readonly_codenames,
    )
    operator_permissions = Permission.objects.filter(
        content_type__app_label='dashboard',
        codename__in=operator_codenames,
    )

    readonly_group.permissions.set(readonly_permissions)
    operator_group.permissions.set(operator_permissions)


def unseed_default_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['Jen čtení', 'Operátor']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0010_alter_automationrule_options_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_default_roles, unseed_default_roles),
    ]

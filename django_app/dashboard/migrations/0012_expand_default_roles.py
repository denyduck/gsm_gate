from django.db import migrations


def _set_group_permissions(Group, Permission, group_name, codenames):
    group, _ = Group.objects.get_or_create(name=group_name)
    permissions = Permission.objects.filter(
        content_type__app_label='dashboard',
        codename__in=codenames,
    )
    group.permissions.set(permissions)


def expand_default_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    view_all = [
        'view_phonenumber',
        'view_group',
        'view_gatewaysettings',
        'view_rule',
        'view_automationrule',
        'view_incomingeventlog',
        'view_outgoingaction',
    ]

    _set_group_permissions(Group, Permission, 'Jen čtení', view_all)

    _set_group_permissions(
        Group,
        Permission,
        'Čísla - přidávání',
        [
            'view_phonenumber',
            'add_phonenumber',
            'view_group',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Skupiny - přidávání',
        [
            'view_group',
            'add_group',
            'view_phonenumber',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Akce - přidávání',
        [
            'view_automationrule',
            'add_automationrule',
            'view_phonenumber',
            'view_group',
            'add_incomingeventlog',
            'view_incomingeventlog',
            'view_outgoingaction',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Správce konfigurace',
        [
            'view_gatewaysettings',
            'change_gatewaysettings',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Operátor',
        [
            'view_phonenumber',
            'add_phonenumber',
            'change_phonenumber',
            'delete_phonenumber',
            'view_group',
            'add_group',
            'change_group',
            'delete_group',
            'view_automationrule',
            'add_automationrule',
            'change_automationrule',
            'delete_automationrule',
            'add_incomingeventlog',
            'view_incomingeventlog',
            'view_outgoingaction',
            'view_gatewaysettings',
            'change_gatewaysettings',
        ],
    )


def rollback_expand_default_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(
        name__in=[
            'Čísla - přidávání',
            'Skupiny - přidávání',
            'Akce - přidávání',
            'Správce konfigurace',
            'Operátor',
            'Jen čtení',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0011_seed_default_roles'),
    ]

    operations = [
        migrations.RunPython(expand_default_roles, rollback_expand_default_roles),
    ]

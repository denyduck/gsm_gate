from django.db import migrations


def _set_group_permissions(Group, Permission, group_name, codenames):
    group, _ = Group.objects.get_or_create(name=group_name)
    permissions = Permission.objects.filter(
        content_type__app_label='dashboard',
        codename__in=codenames,
    )
    group.permissions.set(permissions)


def seed_blocked_number_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Nová granulární role pro správu blokovaných čísel.
    _set_group_permissions(
        Group,
        Permission,
        'Blokovaná čísla - správa',
        [
            'view_blockednumber',
            'add_blockednumber',
            'delete_blockednumber',
        ],
    )

    # Rozšíření existujících rolí (musí obsahovat kompletní seznam, jinak by
    # se ostatní oprávnění skupiny přepsáním ztratila - stejný vzor jako
    # v migraci 0012).
    _set_group_permissions(
        Group,
        Permission,
        'Jen čtení',
        [
            'view_phonenumber',
            'view_group',
            'view_gatewaysettings',
            'view_rule',
            'view_automationrule',
            'view_incomingeventlog',
            'view_outgoingaction',
            'view_blockednumber',
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
            'view_blockednumber',
            'add_blockednumber',
            'delete_blockednumber',
        ],
    )


def rollback_blocked_number_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    Group.objects.filter(name='Blokovaná čísla - správa').delete()

    _set_group_permissions(
        Group,
        Permission,
        'Jen čtení',
        [
            'view_phonenumber',
            'view_group',
            'view_gatewaysettings',
            'view_rule',
            'view_automationrule',
            'view_incomingeventlog',
            'view_outgoingaction',
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


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0036_blockednumber'),
    ]

    operations = [
        migrations.RunPython(seed_blocked_number_roles, rollback_blocked_number_roles),
    ]

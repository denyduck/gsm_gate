from django.db import migrations


def _set_group_permissions(Group, Permission, group_name, codenames):
    group, _ = Group.objects.get_or_create(name=group_name)
    permissions = Permission.objects.filter(
        content_type__app_label='dashboard',
        codename__in=codenames,
    )
    group.permissions.set(permissions)


def seed_granular_rules_action_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    _set_group_permissions(
        Group,
        Permission,
        'Pravidla - čtení',
        [
            'view_automationrule',
            'view_rule',
            'view_phonenumber',
            'view_group',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Pravidla - přidávání',
        [
            'view_automationrule',
            'add_automationrule',
            'view_rule',
            'view_phonenumber',
            'view_group',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Pravidla - správa',
        [
            'view_automationrule',
            'add_automationrule',
            'change_automationrule',
            'delete_automationrule',
            'view_rule',
            'view_phonenumber',
            'view_group',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Odchozí akce - čtení',
        [
            'view_outgoingaction',
            'view_incomingeventlog',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Odchozí akce - správa',
        [
            'view_outgoingaction',
            'add_outgoingaction',
            'change_outgoingaction',
            'delete_outgoingaction',
            'view_incomingeventlog',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Logy událostí - čtení',
        [
            'view_incomingeventlog',
            'view_outgoingaction',
        ],
    )

    _set_group_permissions(
        Group,
        Permission,
        'Simulace událostí',
        [
            'add_incomingeventlog',
            'view_incomingeventlog',
            'view_outgoingaction',
            'view_automationrule',
        ],
    )


def rollback_granular_rules_action_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(
        name__in=[
            'Pravidla - čtení',
            'Pravidla - přidávání',
            'Pravidla - správa',
            'Odchozí akce - čtení',
            'Odchozí akce - správa',
            'Logy událostí - čtení',
            'Simulace událostí',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0012_expand_default_roles'),
    ]

    operations = [
        migrations.RunPython(seed_granular_rules_action_roles, rollback_granular_rules_action_roles),
    ]

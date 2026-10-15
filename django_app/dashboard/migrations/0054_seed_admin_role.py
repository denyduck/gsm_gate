from django.db import migrations


ADMIN_GROUP_NAME = 'Admin'


def seed_admin_role(apps, schema_editor):
    """Třetí úroveň práv (super admin > admin > user) - viz dashboard.access.is_admin.
    Admin dostává zjednodušeně VŠECHNA práva pro dashboard app + auth (správa
    uživatelů) - ne vybraný seznam codenames jako u ostatních rolí níže,
    záměrně, ať se na nic nezapomene a role se "nerozsype" při přidání
    nového modelu v budoucnu. Pro skutečný přístup do Django Admin (/admin/)
    navíc potřebuje i is_staff=True na konkrétním uživateli - to migraci
    neumí (je to vlastnost účtu, ne role)."""
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    permissions = Permission.objects.filter(content_type__app_label__in=['dashboard', 'auth'])
    admin_group.permissions.set(permissions)


def unseed_admin_role(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name=ADMIN_GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0053_phonenumber_contact_fields'),
    ]

    operations = [
        migrations.RunPython(seed_admin_role, unseed_admin_role),
    ]

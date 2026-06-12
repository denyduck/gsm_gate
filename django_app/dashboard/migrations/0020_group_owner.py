from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def set_group_owner_from_members(apps, schema_editor):
    Group = apps.get_model('dashboard', 'Group')

    for group in Group.objects.filter(owner__isnull=True).iterator():
        first_user = group.users.order_by('id').first()
        if first_user is not None:
            group.owner = first_user
            group.save(update_fields=['owner'])


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0019_usergroupvisibilityoverride'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_groups', to=settings.AUTH_USER_MODEL, verbose_name='Vlastník'),
        ),
        migrations.RunPython(set_group_owner_from_members, migrations.RunPython.noop),
    ]

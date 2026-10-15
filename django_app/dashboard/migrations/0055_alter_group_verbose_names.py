from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Jen přejmenování (verbose_name/verbose_name_plural), žádná změna DB
    schématu - rozlišení od Django auth.Group ("Uživatelské skupiny") v celé
    appce, viz role-a-opravneni.md."""

    dependencies = [
        ('dashboard', '0054_seed_admin_role'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='group',
            options={
                'verbose_name': 'Skupina telefonních čísel',
                'verbose_name_plural': 'Skupiny telefonních čísel',
            },
        ),
        migrations.AlterModelOptions(
            name='usergroupvisibilityoverride',
            options={
                'verbose_name': 'Výjimka viditelnosti skupiny telefonních čísel',
                'verbose_name_plural': 'Výjimky viditelnosti skupin telefonních čísel',
            },
        ),
        migrations.AlterField(
            model_name='usergroupvisibilityoverride',
            name='group',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='visibility_overrides',
                to='dashboard.group',
                verbose_name='Skupina telefonních čísel',
            ),
        ),
    ]

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0021_automationrule_message_flag'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='users',
            field=models.ManyToManyField(blank=True, related_name='shared_automation_rules', to=settings.AUTH_USER_MODEL, verbose_name='Přiřazení uživatelé'),
        ),
    ]

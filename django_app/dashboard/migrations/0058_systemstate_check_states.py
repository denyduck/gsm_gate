from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0057_automationrule_system_event_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemstate',
            name='check_states',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Poslední známý status (OK/WARN/ERROR) jednotlivých kontrol zdraví brány - viz services/system_health.py. Slouží jen k detekci ZMĚNY stavu, ať se při přetrvávajícím problému nespamuje notifikace každý cyklus.',
                verbose_name='Stav periodických kontrol',
            ),
        ),
    ]

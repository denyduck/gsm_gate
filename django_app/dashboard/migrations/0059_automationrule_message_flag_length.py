from django.db import migrations, models


class Migration(migrations.Migration):
    """Rozšíření délky message_flag (60 -> 150), ať se vejde víc příznaků
    oddělených čárkou (OR shoda) - viz services/rules_engine.py
    rule_matches_event()."""

    dependencies = [
        ('dashboard', '0058_systemstate_check_states'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationrule',
            name='message_flag',
            field=models.CharField(
                blank=True,
                help_text='Víc příznaků najednou (ANY) odděl čárkou, např. "#REBOOT,#LOGIN_ATTACK".',
                max_length=150,
                verbose_name='Příznak v SMS',
            ),
        ),
    ]

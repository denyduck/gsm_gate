from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0016_alter_automationrule_action_label'),
    ]

    operations = [
        migrations.AlterField(
            model_name='outgoingaction',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('NOTIFY_SMS', 'Notifikační SMS'),
                    ('FORWARD_INFO', 'Předání na číslo'),
                ],
                max_length=20,
                verbose_name='Typ akce',
            ),
        ),
    ]

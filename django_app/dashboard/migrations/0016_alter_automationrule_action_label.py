from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0015_split_notify_actions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationrule',
            name='action',
            field=models.CharField(
                choices=[
                    ('IGNORE', 'Ignorovat'),
                    ('NOTIFY_NUM', 'Poslat informaci na cílová čísla'),
                    ('NOTIFY_GRP', 'Poslat informaci na cílové skupiny'),
                    ('FORWARD', 'Předat na číslo'),
                ],
                default='IGNORE',
                max_length=10,
                verbose_name='Reakce',
            ),
        ),
    ]

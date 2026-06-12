from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0026_automationrule_source_objects'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='notify_via_email',
            field=models.BooleanField(default=False, verbose_name='Notifikovat přes e-mail'),
        ),
        migrations.AddField(
            model_name='automationrule',
            name='notify_via_sms',
            field=models.BooleanField(default=True, verbose_name='Notifikovat přes SMS'),
        ),
        migrations.AddField(
            model_name='automationrule',
            name='notify_via_teams',
            field=models.BooleanField(default=False, verbose_name='Notifikovat do Teams'),
        ),
    ]

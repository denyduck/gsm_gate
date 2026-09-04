from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0043_selftestrun_counts'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='notify_first_contact',
            field=models.BooleanField(
                default=False,
                help_text='Když tohle pravidlo osloví dané cílové číslo poprvé, pošle navíc jednorázovou informační SMS (text níže).',
                verbose_name='Odeslat informační SMS při prvním kontaktu čísla',
            ),
        ),
        migrations.AddField(
            model_name='automationrule',
            name='first_contact_message',
            field=models.CharField(
                blank=True,
                help_text='Např. "Bylo jsi zařazen do automatizace X, důvod: ...". Odešle se jen jednou na dané číslo, při prvním kontaktu tímto pravidlem.',
                max_length=320,
                verbose_name='Text informační SMS',
            ),
        ),
        migrations.AlterField(
            model_name='outgoingaction',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('NOTIFY_SMS', 'Notifikační SMS'),
                    ('NOTIFY_EMAIL', 'Notifikační e-mail'),
                    ('NOTIFY_TEAMS', 'Notifikace do Teams'),
                    ('FORWARD_INFO', 'Předání na číslo'),
                    ('DEVICE_PULL', 'Vyzvednutí požadavku objektu'),
                    ('INFO_SMS', 'Informační SMS (první kontakt)'),
                ],
                max_length=20,
                verbose_name='Typ akce',
            ),
        ),
    ]

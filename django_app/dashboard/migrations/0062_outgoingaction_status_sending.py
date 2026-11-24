from django.db import migrations, models


class Migration(migrations.Migration):
    """Stav SENDING - worker si akci před odesláním atomicky zabere, ať ji
    souběžně běžící druhá instance workeru nepošle podruhé (zdvojená SMS)."""

    dependencies = [
        ('dashboard', '0061_sms_dispatch_retry_own_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='outgoingaction',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Čeká'), ('SENDING', 'Odesílá se'), ('SENT', 'Odesláno'),
                    ('FAILED', 'Chyba'), ('CANCELLED', 'Zrušeno'),
                ],
                default='PENDING', max_length=10, verbose_name='Stav',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0052_automationrule_first_contact_timing_blank'),
    ]

    operations = [
        migrations.AddField(
            model_name='phonenumber',
            name='first_name',
            field=models.CharField(blank=True, max_length=100, verbose_name='Jméno'),
        ),
        migrations.AddField(
            model_name='phonenumber',
            name='last_name',
            field=models.CharField(blank=True, max_length=100, verbose_name='Příjmení'),
        ),
        migrations.AddField(
            model_name='phonenumber',
            name='role',
            field=models.CharField(blank=True, max_length=100, verbose_name='Funkce'),
        ),
        migrations.AddField(
            model_name='phonenumber',
            name='note',
            field=models.TextField(blank=True, verbose_name='Poznámka'),
        ),
    ]

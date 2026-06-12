from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0020_group_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='message_flag',
            field=models.CharField(blank=True, max_length=60, verbose_name='Příznak v SMS'),
        ),
        migrations.AddField(
            model_name='automationrule',
            name='use_message_flag',
            field=models.BooleanField(default=False, verbose_name='Filtrovat podle příznaku v SMS'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0025_deviceobject_object_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='source_objects',
            field=models.ManyToManyField(blank=True, related_name='source_automation_rules', to='dashboard.deviceobject', verbose_name='Zdrojové objekty'),
        ),
    ]

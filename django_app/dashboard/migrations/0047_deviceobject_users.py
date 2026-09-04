from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0046_merge_any_into_sms_api_event_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceobject',
            name='users',
            field=models.ManyToManyField(
                blank=True,
                related_name='shared_device_objects',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Uživatelé se sdílením',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0024_deviceobjectapicredential'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceobject',
            name='object_label',
            field=models.CharField(blank=True, max_length=120, verbose_name='Vlastní popisek objektu'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0042_selftestrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='selftestrun',
            name='ok_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Počet OK'),
        ),
        migrations.AddField(
            model_name='selftestrun',
            name='warn_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Počet varování'),
        ),
        migrations.AddField(
            model_name='selftestrun',
            name='error_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Počet chyb'),
        ),
    ]

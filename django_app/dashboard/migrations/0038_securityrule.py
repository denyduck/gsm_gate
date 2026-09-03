import django.core.validators
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0037_seed_blocked_number_roles'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SecurityRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=True, verbose_name='Aktivní')),
                ('rate_limit_window_minutes', models.PositiveIntegerField(default=10, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1440)], verbose_name='Časové okno (min)')),
                ('rate_limit_max_events', models.PositiveIntegerField(default=20, validators=[django.core.validators.MinValueValidator(1)], verbose_name='Max. událostí v okně')),
                ('auto_block_cooldown_minutes', models.PositiveIntegerField(default=30, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10080)], verbose_name='Doba automatické blokace (min)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Naposledy změněno')),
                ('owner', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='security_rule', to=settings.AUTH_USER_MODEL, verbose_name='Vlastník')),
            ],
            options={
                'verbose_name': 'Bezpečnostní pravidlo',
                'verbose_name_plural': 'Bezpečnostní pravidla',
            },
        ),
    ]

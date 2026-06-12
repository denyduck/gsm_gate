from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0018_add_source_groups'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserGroupVisibilityOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visibility_overrides', to='dashboard.group', verbose_name='Skupina')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_visibility_overrides', to=settings.AUTH_USER_MODEL, verbose_name='Uživatel')),
                ('hidden_numbers', models.ManyToManyField(blank=True, related_name='hidden_in_visibility_overrides', to='dashboard.phonenumber', verbose_name='Skrytá čísla')),
            ],
            options={
                'verbose_name': 'Výjimka viditelnosti skupiny',
                'verbose_name_plural': 'Výjimky viditelnosti skupin',
            },
        ),
        migrations.AddConstraint(
            model_name='usergroupvisibilityoverride',
            constraint=models.UniqueConstraint(fields=('user', 'group'), name='unique_user_group_visibility_override'),
        ),
    ]

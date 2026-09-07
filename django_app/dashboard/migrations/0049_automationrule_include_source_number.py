from django.db import migrations, models


def preserve_current_display(apps, schema_editor):
    """Zachovat současné chování pro už existující pravidla: dřív se zdrojové
    číslo objevovalo jen v automaticky generovaném textu (bez custom_message).
    Pravidla s vlastním textem číslo nikdy nezobrazovala - u nich vypnout
    include_source_number, ať se jim náhle "neobjeví" nový obsah ve zprávě.
    Pravidla bez vlastního textu mají výchozí True beze změny."""
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    AutomationRule.objects.exclude(custom_message='').update(include_source_number=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0048_first_contact_timing'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationrule',
            name='include_source_number',
            field=models.BooleanField(
                default=True,
                help_text='Uplatní se hlavně u příchozí SMS/SMS i API – do zprávy předávané dál (na čísla/skupiny) se přidá, od jakého čísla událost přišla.',
                verbose_name='Zobrazit zdrojové číslo ve zprávě',
            ),
        ),
        migrations.RunPython(preserve_current_display, noop),
    ]

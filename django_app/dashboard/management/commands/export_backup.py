import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from dashboard.services import backup as backup_service


class Command(BaseCommand):
    help = 'Vyexportuje data brány (dumpdata) do timestamped JSON souboru - pro plánované zálohy přes cron/systemd timer.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--kind',
            choices=sorted(backup_service.MODEL_SETS.keys()),
            default='data',
            help='Co zálohovat: "data" (vše) nebo "settings" (jen nastavení brány). Výchozí: data.',
        )
        parser.add_argument(
            '--output-dir',
            default='backups',
            help='Kam uložit výstupní soubor (relativně k projektu, nebo absolutní cesta). Výchozí: backups/.',
        )

    def handle(self, *args, **options):
        kind = options['kind']
        output_dir = options['output_dir']

        os.makedirs(output_dir, exist_ok=True)

        content = backup_service.dump_models(backup_service.MODEL_SETS[kind])
        filename = f'gsm_gate_{kind}_backup_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
        output_path = os.path.join(output_dir, filename)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except OSError as exc:
            raise CommandError(f'Nepodařilo se zapsat zálohu do {output_path}: {exc}') from exc

        self.stdout.write(self.style.SUCCESS(f'Záloha ({kind}) uložena do {output_path}'))

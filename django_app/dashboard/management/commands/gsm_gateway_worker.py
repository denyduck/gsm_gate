import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError

from dashboard.services.gsm_worker import GsmWorkerService


class Command(BaseCommand):
    help = 'Spustí worker pro SIM7000 (příchozí SMS + odchozí akce z fronty).'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=settings.GSM_WORKER_INTERVAL)
        parser.add_argument('--once', action='store_true', help='Provede pouze jeden cyklus workeru.')

    def handle(self, *args, **options):
        if not settings.GSM_ENABLED:
            self.stdout.write(self.style.WARNING('GSM worker je vypnutý (GSM_ENABLED=false).'))
            return

        interval = max(1, options['interval'])
        run_once = options['once']

        worker = GsmWorkerService()
        self.stdout.write(self.style.SUCCESS('GSM worker spuštěn.'))

        try:
            while True:
                try:
                    result = worker.cycle()
                    self.stdout.write(
                        f'Cyklus dokončen: incoming={result.incoming_processed}, '
                        f'sent={result.outgoing_sent}, failed={result.outgoing_failed}'
                    )
                except OperationalError as e:
                    self.stdout.write(self.style.WARNING(f'DB chyba, čekám 15s a zkouším znovu: {e}'))
                    time.sleep(15)
                    continue

                if run_once:
                    break

                time.sleep(interval)
        finally:
            worker.close()
            self.stdout.write(self.style.WARNING('GSM worker ukončen.'))

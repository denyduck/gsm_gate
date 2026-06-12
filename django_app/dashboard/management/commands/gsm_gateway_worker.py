import time

from django.conf import settings
from django.core.management.base import BaseCommand

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
                result = worker.cycle()
                self.stdout.write(
                    f'Cyklus dokončen: incoming={result.incoming_processed}, '
                    f'sent={result.outgoing_sent}, failed={result.outgoing_failed}'
                )

                if run_once:
                    break

                time.sleep(interval)
        finally:
            worker.close()
            self.stdout.write(self.style.WARNING('GSM worker ukončen.'))

import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError

from dashboard.services.gsm_worker import GsmWorkerService
from dashboard.services.modem_manager import ModemError

logger = logging.getLogger(__name__)

# Pro Docker healthcheck (docker-compose.yml) - dotkne se souboru při každém
# průchodu smyčkou, ať úspěšném nebo ne. Healthcheck jen kontroluje stáří
# souboru (je smyčka vůbec živá?), ne jestli poslední cyklus uspěl.
HEARTBEAT_PATH = Path('/tmp/gsm_worker_heartbeat')


def _touch_heartbeat():
    try:
        HEARTBEAT_PATH.touch()
    except OSError:
        pass


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
                _touch_heartbeat()

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
                except ModemError as e:
                    self.stdout.write(self.style.WARNING(f'Modem chyba, čekám 10s a zkouším znovu: {e}'))
                    worker.close()
                    time.sleep(10)
                    continue
                except Exception as e:
                    logger.exception('Neočekávaná chyba v cyklu workeru')
                    self.stdout.write(self.style.ERROR(f'Neočekávaná chyba, čekám 10s a zkouším znovu: {e}'))
                    worker.close()
                    time.sleep(10)
                    continue

                if run_once:
                    break

                time.sleep(interval)
        finally:
            worker.close()
            self.stdout.write(self.style.WARNING('GSM worker ukončen.'))

from django.conf import settings
from django.core.management.base import BaseCommand

from dashboard.services import retention


class Command(BaseCommand):
    help = 'Smaže staré záznamy (IncomingEventLog + navázané OutgoingAction, SignalReading) podle retenční politiky.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--logs-days',
            type=int,
            default=settings.RETENTION_DAYS_LOGS,
            help=f'Smazat IncomingEventLog (a jejich OutgoingAction) starší než N dní. Výchozí: {settings.RETENTION_DAYS_LOGS}.',
        )
        parser.add_argument(
            '--signal-days',
            type=int,
            default=settings.RETENTION_DAYS_SIGNAL_HISTORY,
            help=f'Smazat SignalReading starší než N dní. Výchozí: {settings.RETENTION_DAYS_SIGNAL_HISTORY}.',
        )

    def handle(self, *args, **options):
        logs_days = options['logs_days']
        signal_days = options['signal_days']

        logs_deleted = retention.prune_event_logs(logs_days)
        signal_deleted = retention.prune_signal_history(signal_days)

        self.stdout.write(self.style.SUCCESS(
            f'Smazáno {logs_deleted} záznamů (IncomingEventLog + OutgoingAction) starších {logs_days} dní '
            f'a {signal_deleted} záznamů SignalReading starších {signal_days} dní.'
        ))

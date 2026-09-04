"""Retenční politika pro rostoucí tabulky - viz management příkaz
prune_old_data a scripts/gsm-prune.timer. Doplněk k ručnímu "Reset dat"
na stránce Zálohování, ne náhrada."""

from datetime import timedelta

from django.utils import timezone

from dashboard.models import IncomingEventLog, SignalReading


def prune_event_logs(days):
    """Smaže IncomingEventLog starší než `days` dní. OutgoingAction.event_log
    je on_delete=CASCADE, takže se smažou i navázané odchozí akce - není
    potřeba mazat OutgoingAction zvlášť."""
    cutoff = timezone.now() - timedelta(days=days)
    count, _ = IncomingEventLog.objects.filter(created_at__lt=cutoff).delete()
    return count


def prune_signal_history(days):
    cutoff = timezone.now() - timedelta(days=days)
    count, _ = SignalReading.objects.filter(recorded_at__lt=cutoff).delete()
    return count

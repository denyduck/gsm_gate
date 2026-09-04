from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from dashboard.models import IncomingEventLog, OutgoingAction, PhoneNumber
from dashboard.services.rules_engine import normalize_phone_number

# Typy odchozích akcí, které reálně znamenají SMS na telefonní číslo (ne
# e-mail/Teams) - viz gsm_worker.py, kde všechny tři padají do stejné
# obecné cesty odeslání SMS.
SMS_ACTION_TYPES = ['NOTIFY_SMS', 'FORWARD_INFO', 'INFO_SMS']

NON_PHONE_TARGETS = ('MAIL', 'TEAMS')


def summary_counts(user):
    sms_actions = OutgoingAction.objects.filter(owner=user, action_type__in=SMS_ACTION_TYPES)
    return {
        'total_sms': sms_actions.count(),
        'sent': sms_actions.filter(status='SENT').count(),
        'failed': sms_actions.filter(status='FAILED').count(),
        'pending': sms_actions.filter(status='PENDING').count(),
        'total_incoming_events': IncomingEventLog.objects.filter(owner=user).count(),
    }


def daily_sms_series(user, days=30):
    since = timezone.now() - timedelta(days=days)
    rows = (
        OutgoingAction.objects
        .filter(owner=user, action_type__in=SMS_ACTION_TYPES, status='SENT', created_at__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
    )
    by_day = {row['day']: row['count'] for row in rows}

    labels = []
    values = []
    for offset in range(days, -1, -1):
        day = (timezone.now() - timedelta(days=offset)).date()
        labels.append(day.strftime('%d.%m.'))
        values.append(by_day.get(day, 0))

    return labels, values


def sms_by_rule(user, limit=10):
    rows = (
        OutgoingAction.objects
        .filter(owner=user, action_type__in=SMS_ACTION_TYPES, status='SENT', rule__isnull=False)
        .values('rule__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )
    labels = [row['rule__name'] for row in rows]
    values = [row['count'] for row in rows]
    return labels, values


def sms_by_target_number(user, limit=10):
    rows = (
        OutgoingAction.objects
        .filter(owner=user, action_type__in=SMS_ACTION_TYPES, status='SENT')
        .exclude(target_number__in=NON_PHONE_TARGETS)
        .values('target_number')
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )
    labels = [row['target_number'] for row in rows]
    values = [row['count'] for row in rows]
    return labels, values


def events_by_source_number(user, limit=10):
    rows = (
        IncomingEventLog.objects
        .filter(owner=user)
        .exclude(source_number='')
        .values('source_number')
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )
    labels = [row['source_number'] for row in rows]
    values = [row['count'] for row in rows]
    return labels, values


def sms_by_group(user, limit=10):
    """Kolik odeslaných SMS šlo číslům patřícím do dané skupiny. Číslo ve
    více skupinách se započítá do každé z nich - jde o "kolik provozu
    prochází skupinou X", ne o rozklad beze zbytku."""
    rows = (
        OutgoingAction.objects
        .filter(owner=user, action_type__in=SMS_ACTION_TYPES, status='SENT')
        .exclude(target_number__in=NON_PHONE_TARGETS)
        .values('target_number')
        .annotate(count=Count('id'))
    )
    counts_by_number = {row['target_number']: row['count'] for row in rows}

    group_totals = {}
    numbers = PhoneNumber.objects.filter(owner=user).prefetch_related('groups')
    for phone in numbers:
        count = counts_by_number.get(normalize_phone_number(phone.number), 0)
        if not count:
            continue
        for group in phone.groups.all():
            group_totals[group.name] = group_totals.get(group.name, 0) + count

    top = sorted(group_totals.items(), key=lambda item: -item[1])[:limit]
    labels = [name for name, _ in top]
    values = [count for _, count in top]
    return labels, values

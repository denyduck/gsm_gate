"""Plánovač odchozích SMS - vyhodnocení PŘED bránou a po selhání.

Princip (viz docs/funkcionalita.md, Odeslání SMS):

1. Příprava: příjemci hromadné SMS se před uložením normalizují, odstraní
   se duplicity, neplatná čísla a číslo brány (plan_recipients). Uživatel
   vidí náhled a odhad doby a teprve pak potvrdí.
2. Odeslání: worker zkouší každou SMS JEN JEDNOU za průchod - nikdy nečeká
   a neopakuje ji na místě, ať jedna problémová SMS nezdrží ostatní.
3. Po selhání se SMS vrátí sem (schedule_retry_or_fail): trvalá chyba
   (neplatné číslo/text, číslo brány) -> hned FAILED; dočasná chyba (modem,
   timeout) -> zpět do fronty s odstupem (RETRY_BACKOFF), zařazená za SMS,
   které ještě nebyly zkoušené; po vyčerpání pokusů FAILED s možností
   ručně „Poslat znovu“ (requeue).

Ochrana proti smyčce:
- číslo brány (GatewaySettings.own_number) - brána na něj nikdy nepošle a
  příchozí SMS z něj ignoruje,
- ping-pong (pingpong_rounds) - číslo, které opakovaně odpovídá na SMS,
  jež mu pravidla posílají jako reakci na jeho vlastní zprávy, dočasně
  nedostává další SMS zpět, viz rules_engine.process_incoming_event.
"""

import re
import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, List

from django.utils import timezone

from dashboard.models import GatewaySettings, OutgoingAction

SMS_ACTION_TYPES = ('NOTIFY_SMS', 'FORWARD_INFO', 'INFO_SMS')

# Odstupy mezi pokusy po dočasné chybě: 1. opakování za 1 min, 2. za 5 min,
# 3. za 15 min. Celkem tedy 4 pokusy.
RETRY_BACKOFF = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15)]
MAX_ATTEMPTS = len(RETRY_BACKOFF) + 1

# Ping-pong: když číslo za PINGPONG_WINDOW už PINGPONG_MAX_ROUNDS× dostalo
# SMS z pravidla jako reakci na svou vlastní zprávu, další SMS zpět na něj se
# pozastaví (pravděpodobně automaticky odpovídající zařízení = smyčka).
PINGPONG_WINDOW = timedelta(minutes=10)
PINGPONG_MAX_ROUNDS = 3

DEFAULT_SECONDS_PER_SMS = 6.0

_VALID_NUMBER_RE = re.compile(r'^\+?\d{3,15}$')


def canonical_number(raw) -> str:
    """Sjednotí zápis čísla pro porovnání: 00420… i 420… i 9místné české
    číslo -> +420…. Jen pro porovnávání, uložené hodnoty se nemění."""
    value = ''.join(ch for ch in (raw or '').strip() if ch.isdigit() or ch == '+')
    if value.startswith('00'):
        value = '+' + value[2:]
    if len(value) == 9 and value.isdigit() and value[0] != '0':
        value = '+420' + value
    elif len(value) == 12 and value.startswith('420') and value.isdigit():
        value = '+' + value
    return value


def number_variants(raw) -> set:
    """Všechny běžné zápisy téhož čísla - pro dotazy nad uloženými čísly,
    která můžou být v libovolném z těchto tvarů."""
    canon = canonical_number(raw)
    variants = {canon}
    if canon.startswith('+420') and len(canon) == 13:
        local = canon[4:]
        variants |= {local, '00420' + local, '420' + local}
    variants.discard('')
    return variants


def gateway_numbers() -> set:
    return {
        canonical_number(value)
        for value in GatewaySettings.objects.exclude(own_number='').values_list('own_number', flat=True)
        if canonical_number(value)
    }


def is_gateway_number(raw, numbers=None) -> bool:
    canon = canonical_number(raw)
    if not canon:
        return False
    return canon in (gateway_numbers() if numbers is None else numbers)


def pingpong_rounds(raw, window=None) -> int:
    """Kolikrát za okno pravidla poslala číslu SMS jako reakci na jeho
    VLASTNÍ zprávu (zdroj události = cíl SMS). Člověk, který si nechává
    přeposílat zprávy, na to narazí jen výjimečně; automaticky odpovídající
    zařízení v řádu minut - podle toho se pozná smyčka."""
    variants = number_variants(raw)
    if not variants:
        return 0
    return OutgoingAction.objects.filter(
        rule__isnull=False,
        action_type__in=SMS_ACTION_TYPES,
        target_number__in=variants,
        event_log__source_number__in=variants,
        created_at__gte=timezone.now() - (window or PINGPONG_WINDOW),
    ).count()


@dataclass
class RecipientPlan:
    valid: List[str] = field(default_factory=list)
    invalid: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    gateway: List[str] = field(default_factory=list)

    @property
    def excluded_count(self):
        return len(self.invalid) + len(self.duplicates) + len(self.gateway)


def plan_recipients(numbers: Iterable[str]) -> RecipientPlan:
    """Vyhodnocení příjemců před uložením do fronty - pořadí odeslání je
    pořadí, v jakém čísla přišla (po odstranění vyřazených)."""
    plan = RecipientPlan()
    own = gateway_numbers()
    seen = set()
    for raw in numbers:
        number = (raw or '').strip()
        canon = canonical_number(number)
        if not _VALID_NUMBER_RE.match(number.replace(' ', '')) or not canon:
            plan.invalid.append(number)
            continue
        if canon in own:
            plan.gateway.append(number)
            continue
        if canon in seen:
            plan.duplicates.append(number)
            continue
        seen.add(canon)
        plan.valid.append(number)
    return plan


def estimate_seconds_per_sms() -> float:
    """Medián odstupu mezi posledními odeslanými SMS (reálná rychlost
    modemu), jinak konzervativní výchozí hodnota."""
    times = list(
        OutgoingAction.objects.filter(status='SENT', action_type__in=SMS_ACTION_TYPES, processed_at__isnull=False)
        .order_by('-processed_at')
        .values_list('processed_at', flat=True)[:50]
    )
    gaps = [
        (newer - older).total_seconds()
        for newer, older in zip(times, times[1:])
        if 0 < (newer - older).total_seconds() < 120
    ]
    if len(gaps) < 5:
        return DEFAULT_SECONDS_PER_SMS
    return max(1.0, statistics.median(gaps))


def estimate_duration_text(count: int) -> str:
    seconds = int(count * estimate_seconds_per_sms())
    if seconds < 60:
        return f'{seconds} s'
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes} min {rest} s' if rest else f'{minutes} min'
    hours, minutes = divmod(minutes, 60)
    return f'{hours} h {minutes} min'


def schedule_retry_or_fail(action: OutgoingAction, error: str, permanent: bool = False) -> str:
    """Vyhodnocení po neúspěšném pokusu. Vrací nový stav akce."""
    now = timezone.now()
    action.attempts += 1
    action.processed_at = now

    if permanent:
        action.status = 'FAILED'
        action.next_attempt_at = None
        action.execution_detail = f'Neodesláno (trvalá chyba, opakování nemá smysl): {error}'
    elif action.attempts < MAX_ATTEMPTS:
        action.status = 'PENDING'
        action.next_attempt_at = now + RETRY_BACKOFF[action.attempts - 1]
        action.execution_detail = (
            f'Pokus {action.attempts}/{MAX_ATTEMPTS} selhal: {error}. Další pokus v '
            f'{timezone.localtime(action.next_attempt_at):%H:%M:%S} (zařazeno na konec fronty).'
        )
    else:
        action.status = 'FAILED'
        action.next_attempt_at = None
        action.execution_detail = (
            f'Neodesláno ani po {MAX_ATTEMPTS} pokusech: {error}. Lze odeslat znovu ručně.'
        )

    action.save(update_fields=['status', 'attempts', 'next_attempt_at', 'processed_at', 'execution_detail'])
    return action.status


def requeue(actions) -> int:
    """Ruční „Poslat znovu“ - neúspěšné/zrušené SMS zpět do fronty s
    novou sadou pokusů."""
    return actions.filter(status__in=('FAILED', 'CANCELLED'), action_type__in=SMS_ACTION_TYPES).update(
        status='PENDING',
        attempts=0,
        next_attempt_at=None,
        processed_at=None,
        execution_detail='Ručně zařazeno k opětovnému odeslání.',
    )


def cancel_pending(actions) -> int:
    return actions.filter(status='PENDING').update(
        status='CANCELLED',
        next_attempt_at=None,
        processed_at=timezone.now(),
        execution_detail='Zrušeno uživatelem před odesláním.',
    )

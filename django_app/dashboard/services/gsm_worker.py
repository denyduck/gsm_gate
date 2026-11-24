from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
import re
from typing import List, Optional, Tuple
from urllib import request as urllib_request

from django.conf import settings
from django.core.mail import send_mail
from django.db import close_old_connections
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from dashboard.models import OutgoingAction, GatewaySettings, SignalReading, SystemState
from dashboard.services import sms_dispatch, system_health
from dashboard.services.rules_engine import fire_system_health_event, process_incoming_event, normalize_phone_number
from dashboard.services.modem_manager import ModemManagerClient, ModemError, ModemSms

# Throttling pro SignalReading - i s výchozím 10s cyklem workeru by se bez
# tohohle historie nafoukla o desítky tisíc řádků denně. Výjimka: přechod
# (výpadek <-> obnovení) se zaznamená vždy, hned, ať ho graf nezmešká.
SIGNAL_HISTORY_MIN_INTERVAL = timedelta(minutes=5)

# --- Ochrana paměti SMS v modemu (incident 2026-11) -------------------------
# Hromadné odeslání na stovky čísel nechalo v paměti modemu zbytky odchozích
# SMS (stav "sent"), které se nikdy nemazaly - paměť se zaplnila a modem
# přestal přijímat SMS, takže přestala fungovat všechna pravidla. Viz
# docs/modem-diagnostika.md.
#
# Stavy, které v paměti nemají co dělat (odchozí zbytky, nečitelné) - mažou
# se hned při každém cyklu:
ORPHAN_SMS_STATES = {'sent', 'stored', 'unknown'}
# Přechodné stavy - smažou se, až když v nich SMS visí déle než limit
# (neúplná vícedílná příchozí SMS, zaseknuté odesílání):
STALE_SMS_TIMEOUTS = {
    'receiving': timedelta(minutes=30),
    'sending': timedelta(minutes=10),
}
# Když AT+CPMS? nefunguje (ModemManager bez --debug), zkusit znovu až za:
CPMS_RETRY_INTERVAL = timedelta(hours=1)
# Po vyhození pojistky (GSM_SMS_FAILURE_BREAKER selhání za sebou) se SMS
# neodesílají po tuhle dobu - ať rozbitý modem nespálí celou frontu.
SMS_BREAKER_COOLDOWN = timedelta(minutes=5)
# Akce ve stavu SENDING déle než tohle = odesílání přerušené pádem/restartem
# workeru (jedno odeslání trvá nejvýš ~3 min, viz modem_manager.send_sms).
SENDING_STALE_AFTER = timedelta(minutes=15)

# Akce, které reálně jdou přes modem jako SMS.
SMS_ACTION_TYPES = sms_dispatch.SMS_ACTION_TYPES
# Ruční/hromadné SMS (bez pravidla) - mají nižší prioritu a limit za cyklus.
MANUAL_SMS_Q = Q(rule__isnull=True, action_type__in=SMS_ACTION_TYPES)


def READY_Q():
    """Čekající akce, na které už přišla řada (bez odloženého opakování)."""
    return Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now())

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    incoming_processed: int = 0
    outgoing_sent: int = 0
    outgoing_failed: int = 0
    outgoing_deferred: int = 0
    modem_sms_deleted: int = 0
    more_work: bool = False


class GsmWorkerService:
    def __init__(self):
        self.client = ModemManagerClient(pin_code=self._get_configured_pin_code())
        # Ochrana proti smyčce: když se smazání SMS z modemu (delete_sms)
        # nepovede (nestabilní modem/ModemManager - viz docs/modem-diagnostika.md,
        # incident 2026-09-11), zůstane SMS na SIM ve stavu "received" a
        # read_unread_sms() by ji vracelo znovu každý cyklus navždy - pravidla
        # by se tak vyhodnotila znovu a znovu (reálně pozorováno: desítky
        # duplicitních odchozích SMS během pár minut). Otisk už jednou
        # zpracované SMS (odesílatel+čas+text) si pamatujeme po dobu běhu
        # procesu, ať se nevyhodnotí podruhé, i když se smazání z modemu
        # opakovaně nedaří.
        self._processed_sms_fingerprints = set()

        # Kdy worker poprvé viděl SMS v přechodném stavu (index -> čas), viz
        # STALE_SMS_TIMEOUTS.
        self._first_seen_transient = {}
        self._cpms_retry_at = None
        self._sms_paused_until = None
        self._sms_paused_reason = ''

        # Per-cyklus počitadla, nastavují se v cycle().
        self._cycle_deleted = set()
        self._cycle_delete_failures = 0
        self._storage_used = None
        self._storage_capacity = None
        self._storage_states = {}
        self._storage_source = ''
        self._storage_name = ''
        self._gateway_numbers = set()

    @staticmethod
    def _get_configured_pin_code():
        settings_obj = GatewaySettings.objects.exclude(pin_code='').first()
        return settings_obj.pin_code if settings_obj else None

    def cycle(self) -> WorkerResult:
        close_old_connections()
        result = WorkerResult()

        # Mimo try/except na modem (viz níže) - ať detekce restartu RPi
        # funguje i chvíli po výpadku, než se modem zase zaregistruje v síti.
        # Vlastní try/except, ať chyba tady nikdy nezhatí zbytek cyklu.
        try:
            system_health.check_reboot()
        except Exception:
            logger.exception('Chyba při kontrole restartu RPi')

        try:
            system_health.check_periodic_health()
        except Exception:
            logger.exception('Chyba při periodické kontrole zdraví brány')

        try:
            self.client.connect()
        except ModemError:
            # I neúspěšné připojení je pro historii signálu důležité - bez
            # tohohle by výpadek modemu v Telemetrii nešel vůbec vidět
            # (cyklus by skončil dřív, než se k zápisu vůbec dostal).
            self._update_signal_quality()
            raise

        self._cycle_deleted = set()
        self._cycle_delete_failures = 0

        modem_messages = self.client.list_sms()
        result.incoming_processed += self._process_incoming_sms(modem_messages)
        remaining_states = self._sweep_modem_storage(modem_messages)
        result.modem_sms_deleted = len(self._cycle_deleted)
        self._update_storage_status(remaining_states)

        sent, failed, deferred = self._process_outgoing_actions()
        result.outgoing_sent += sent
        result.outgoing_failed += failed
        result.outgoing_deferred += deferred
        self._save_storage_status()
        result.more_work = self.has_ready_work()
        self._update_signal_quality()

        return result

    # --- Paměť SMS v modemu -------------------------------------------------

    def _delete_from_modem(self, index: int) -> bool:
        try:
            self.client.delete_sms(index)
        except ModemError as e:
            self._cycle_delete_failures += 1
            logger.warning('Nepodařilo se smazat SMS z modemu (index %s): %s', index, e)
            return False
        self._cycle_deleted.add(index)
        return True

    def _is_stale_transient(self, sms: ModemSms, now) -> bool:
        timeout = STALE_SMS_TIMEOUTS.get(sms.state)
        if timeout is None:
            return False
        first_seen = self._first_seen_transient.setdefault(sms.index, now)
        return now - first_seen >= timeout

    def _sweep_modem_storage(self, messages: List[ModemSms]) -> Counter:
        """Smaže z modemu zbytky (odchozí SMS, nečitelné, dlouho zaseknuté
        přechodné stavy) a vrátí počty SMS, které v paměti zůstaly, podle
        stavu. Přijaté ("received") řeší _process_incoming_sms - tady se jen
        započítají, pokud se je tam nepodařilo smazat."""
        now = timezone.now()
        present = {m.index for m in messages}
        self._first_seen_transient = {
            idx: seen for idx, seen in self._first_seen_transient.items() if idx in present
        }

        remaining = Counter()
        for sms in messages:
            if sms.index in self._cycle_deleted:
                continue
            if sms.state in ORPHAN_SMS_STATES or self._is_stale_transient(sms, now):
                if self._delete_from_modem(sms.index):
                    logger.warning(
                        'Úklid paměti modemu: smazána SMS index %s (stav %s, číslo %s) - zbytek, který '
                        'by jinak zabíral místo (viz docs/modem-diagnostika.md).',
                        sms.index, sms.state, sms.number or '?',
                    )
                    continue
            remaining[sms.state] += 1
        return remaining

    def _query_cpms(self):
        now = timezone.now()
        if self._cpms_retry_at is not None and now < self._cpms_retry_at:
            return None
        info = self.client.get_storage_info()
        if info is None:
            if self._cpms_retry_at is None:
                logger.info(
                    'AT+CPMS? není dostupné (ModemManager bez --debug) - obsazenost paměti SMS se '
                    'odhaduje z počtu SMS v ModemManageru a GSM_MODEM_SMS_CAPACITY=%s.',
                    settings.GSM_MODEM_SMS_CAPACITY,
                )
            self._cpms_retry_at = now + CPMS_RETRY_INTERVAL
            return None
        self._cpms_retry_at = None
        return info

    def _update_storage_status(self, remaining_states: Counter) -> None:
        self._storage_states = dict(remaining_states)
        self._storage_used = sum(remaining_states.values())
        self._storage_capacity = settings.GSM_MODEM_SMS_CAPACITY
        self._storage_source = 'CONFIG'
        self._storage_name = ''

        info = self._query_cpms()
        if info is not None:
            # Modem zná i SMS, které ModemManager nevidí - jeho čísla mají přednost.
            self._storage_used = info.used
            self._storage_capacity = info.total
            self._storage_source = 'AT'
            self._storage_name = info.storage

    def _storage_percent(self) -> Optional[int]:
        if self._storage_used is None or not self._storage_capacity:
            return None
        return round(100 * self._storage_used / self._storage_capacity)

    def _save_storage_status(self) -> None:
        state = SystemState.load()
        state.modem_sms_used = self._storage_used
        state.modem_sms_capacity = self._storage_capacity
        state.modem_sms_capacity_source = self._storage_source
        state.modem_sms_storage = self._storage_name
        state.modem_sms_states = self._storage_states
        state.modem_sms_delete_failures = self._cycle_delete_failures
        state.modem_sms_checked_at = timezone.now()
        state.sms_sending_paused_reason = self._current_pause_reason()[:255]
        state.save(update_fields=[
            'modem_sms_used', 'modem_sms_capacity', 'modem_sms_capacity_source', 'modem_sms_storage',
            'modem_sms_states', 'modem_sms_delete_failures', 'modem_sms_checked_at',
            'sms_sending_paused_reason',
        ])

    def _current_pause_reason(self) -> str:
        """Důvod, proč se teď SMS neodesílají (prázdný = odesílat lze)."""
        percent = self._storage_percent()
        if percent is not None and percent >= settings.GSM_MODEM_STORAGE_PAUSE_PERCENT:
            return (
                f'Paměť SMS v modemu je zaplněná na {percent} % ({self._storage_used}/{self._storage_capacity}) '
                f'- odesílání SMS pozastaveno, aby zůstalo místo pro příchozí zprávy.'
            )
        if self._sms_paused_until is not None:
            if timezone.now() < self._sms_paused_until:
                return self._sms_paused_reason
            self._sms_paused_until = None
            self._sms_paused_reason = ''
        return ''

    def _update_signal_quality(self) -> None:
        quality = None
        try:
            quality = self.client.get_signal_quality()
        except ModemError as e:
            logger.warning('Nepodařilo se zjistit sílu signálu: %s', e)

        now = timezone.now()
        for settings_obj in GatewaySettings.objects.all():
            settings_obj.last_signal_quality = quality
            settings_obj.last_signal_checked_at = now
            settings_obj.save(update_fields=['last_signal_quality', 'last_signal_checked_at'])
            self._record_signal_reading(settings_obj.user, quality)

    @staticmethod
    def _record_signal_reading(user, quality) -> None:
        last = SignalReading.objects.filter(owner=user).order_by('-recorded_at').first()
        if last is not None:
            changed = last.quality != quality
            recent_enough = (timezone.now() - last.recorded_at) < SIGNAL_HISTORY_MIN_INTERVAL
            if recent_enough and not changed:
                return
        SignalReading.objects.create(owner=user, quality=quality)

    def close(self):
        self.client.close()

    def _process_incoming_sms(self, modem_messages: List[ModemSms]) -> int:
        processed_count = 0

        for item in modem_messages:
            if item.state != 'received':
                continue

            fingerprint = (item.number, item.timestamp, item.text)

            if fingerprint in self._processed_sms_fingerprints:
                logger.warning(
                    'SMS od %s (čas %s) už byla v tomhle běhu workeru zpracovaná, ale pořád je na modemu '
                    '- smazání zřejmě opakovaně selhává. Pravidla se podruhé nevyhodnocují, zkouším smazat znovu.',
                    item.number, item.timestamp,
                )
            else:
                source = normalize_phone_number(item.number)
                settings_owner = GatewaySettings.objects.filter(allow_incoming_sms=True)

                for settings_obj in settings_owner:
                    process_incoming_event(
                        user=settings_obj.user,
                        event_type='SMS',
                        source_number=source,
                        message_body=item.text,
                    )

                self._processed_sms_fingerprints.add(fingerprint)
                processed_count += 1

            self._delete_from_modem(item.index)

        return processed_count

    @staticmethod
    def _select_pending_actions() -> List[OutgoingAction]:
        """Akce z pravidel, systémové notifikace, e-mail/Teams mají přednost
        před ručními/hromadnými SMS (bez pravidla) - a těch se za cyklus
        vezme nejvýš GSM_MAX_MANUAL_SMS_PER_CYCLE. Velké hromadné odeslání se
        tak rozloží do víc cyklů a pravidla nečekají za ním ve frontě."""
        limit = settings.GSM_MAX_ACTIONS_PER_CYCLE
        # Opakované pokusy (next_attempt_at) se řadí podle času, kdy na ně
        # přijde řada - tedy ZA SMS, které čekají od dřív a ještě nebyly
        # zkoušené. Jedna problémová SMS tak nikdy nebrzdí ostatní.
        pending = (
            OutgoingAction.objects.filter(READY_Q(), status='PENDING')
            .annotate(queue_time=Coalesce('next_attempt_at', 'created_at'))
            .order_by('queue_time', 'id')
        )

        priority = list(pending.exclude(MANUAL_SMS_Q)[:limit])
        room = min(limit - len(priority), settings.GSM_MAX_MANUAL_SMS_PER_CYCLE)
        manual = list(pending.filter(MANUAL_SMS_Q)[:room]) if room > 0 else []
        return priority + manual

    def has_ready_work(self) -> bool:
        """Je ve frontě další akce připravená k odeslání HNED? Worker pak
        mezi cykly nečeká (hromadná SMS jede plnou rychlostí modemu, a
        přitom se po každé dávce zkontrolují příchozí SMS a pravidla)."""
        ready = OutgoingAction.objects.filter(READY_Q(), status='PENDING')
        if self._current_pause_reason():
            ready = ready.exclude(action_type__in=SMS_ACTION_TYPES)
        return ready.exists()

    def _trip_sms_breaker(self, consecutive_failures: int) -> None:
        self._sms_paused_until = timezone.now() + SMS_BREAKER_COOLDOWN
        self._sms_paused_reason = (
            f'{consecutive_failures} SMS za sebou se nepodařilo odeslat - odesílání SMS pozastaveno na '
            f'{int(SMS_BREAKER_COOLDOWN.total_seconds() // 60)} min (zbytek fronty čeká, nic se nezahazuje).'
        )
        logger.error('Pojistka odesílání: %s', self._sms_paused_reason)

    def _process_outgoing_actions(self) -> Tuple[int, int, int]:
        sent_count = 0
        failed_count = 0
        deferred_count = 0
        consecutive_sms_failures = 0

        recovered = self.recover_interrupted_sends()
        if recovered:
            logger.error('%s akcí zůstalo ve stavu „Odesílá se“ po přerušení workeru - označeny jako nejisté.', recovered)
        self._gateway_numbers = sms_dispatch.gateway_numbers()
        pending_actions = self._select_pending_actions()
        pause_reason = self._current_pause_reason()
        if pause_reason:
            logger.warning('Odesílání SMS v tomto cyklu neprobíhá: %s', pause_reason)

        for action in pending_actions:
            if action.action_type in SMS_ACTION_TYPES:
                if pause_reason:
                    # Zůstává PENDING - odešle se, až se paměť uvolní / pojistka vyprší.
                    deferred_count += 1
                    continue

                if not self._claim(action):
                    continue

                outcome = self._send_sms_action(action)
                if outcome == 'SENT':
                    sent_count += 1
                    consecutive_sms_failures = 0
                elif outcome == 'REJECTED':
                    # Zamítnuto před modemem (neplatné číslo/text) - modem se
                    # nedotkl, do pojistky se nepočítá.
                    failed_count += 1
                else:
                    failed_count += 1
                    consecutive_sms_failures += 1
                    if consecutive_sms_failures >= settings.GSM_SMS_FAILURE_BREAKER:
                        self._trip_sms_breaker(consecutive_sms_failures)

                pause_reason = self._current_pause_reason()
                continue

            if not self._claim(action):
                continue

            try:
                if action.action_type == 'NOTIFY_EMAIL':
                    self._send_email_notification(action)
                    self._mark_action_result(action, 'SENT', 'E-mail notifikace byla úspěšně odeslána.')
                    sent_count += 1
                    continue

                if action.action_type == 'NOTIFY_TEAMS':
                    self._send_teams_notification(action)
                    self._mark_action_result(action, 'SENT', 'Teams notifikace byla úspěšně odeslána.')
                    sent_count += 1
                    continue

                if action.action_type == 'DEVICE_PULL':
                    self._mark_action_result(action, 'SENT', 'Požadavek DEVICE_PULL byl označen jako zpracovaný.')
                    sent_count += 1
                    continue

                raise ModemError(f'Neznámý typ akce {action.action_type}.')
            except Exception as exc:
                self._mark_action_result(action, 'FAILED', f'Akce selhala: {exc}')
                failed_count += 1

        return sent_count, failed_count, deferred_count

    @staticmethod
    def _claim(action: OutgoingAction) -> bool:
        """Atomicky převede akci PENDING -> SENDING. Když ji mezitím zabrala
        jiná instance workeru (nebo ji uživatel zrušil), vrátí False a akce
        se přeskočí - SMS tak nikdy neodejde dvakrát."""
        claimed = OutgoingAction.objects.filter(pk=action.pk, status='PENDING').update(
            status='SENDING', processed_at=timezone.now(),
        )
        if not claimed:
            logger.warning('Akce %s už není ve stavu Čeká (zabrala ji jiná instance workeru / zrušena) - přeskakuji.', action.pk)
            return False
        action.status = 'SENDING'
        return True

    @staticmethod
    def recover_interrupted_sends() -> int:
        """Akce, které zůstaly ve stavu SENDING (worker spadl/restartoval se
        uprostřed odesílání). Nevíme, jestli SMS odešla - automaticky se
        NEopakují (hrozila by zdvojená SMS), označí se jako neodeslané s
        možností ručně „Poslat znovu“."""
        limit = timezone.now() - SENDING_STALE_AFTER
        stale = OutgoingAction.objects.filter(status='SENDING').filter(
            Q(processed_at__lt=limit) | Q(processed_at__isnull=True)
        )
        return stale.update(
            status='FAILED',
            processed_at=timezone.now(),
            next_attempt_at=None,
            execution_detail=(
                'Nejisté: odesílání bylo přerušeno (restart/pád workeru) a nelze zjistit, zda SMS odešla. '
                'Automaticky se neopakuje, aby nepřišla dvakrát - ověř u příjemce a případně pošli znovu.'
            ),
        )

    def _send_sms_action(self, action: OutgoingAction) -> str:
        """Odešle jednu SMS akci. Vrací 'SENT', 'REJECTED' (zamítnuto ještě
        před modemem) nebo 'FAILED' (selhalo v modemu)."""
        target = normalize_phone_number(action.target_number)
        try:
            if sms_dispatch.is_gateway_number(target, self._gateway_numbers):
                raise ModemError(f'{target} je číslo samotné brány - SMS by se vrátila zpět jako příchozí (smyčka).')
            self.client.validate_sms(target, action.payload_message)
        except ModemError as exc:
            sms_dispatch.schedule_retry_or_fail(
                action, f'zpráva zamítnuta před odesláním (do modemu se nic nezapsalo): {exc}', permanent=True,
            )
            self._after_sms_final(action)
            return 'REJECTED'

        try:
            cleaned = self.client.send_sms(
                target,
                action.payload_message,
                request_delivery_report=self._wants_delivery_report(action),
            )
        except Exception as exc:
            if getattr(exc, 'sms_cleaned', True) is False:
                self._note_leftover_sms()
            # Jeden pokus a dál - o opakování rozhodne plánovač (zařadí SMS
            # na konec fronty s odstupem, nebo ji po vyčerpání pokusů označí
            # jako neodeslanou).
            sms_dispatch.schedule_retry_or_fail(action, str(exc))
            self._after_sms_final(action)
            return 'FAILED'

        if not cleaned:
            self._note_leftover_sms()
        attempt_note = f' (na {action.attempts + 1}. pokus)' if action.attempts else ''
        action.attempts += 1
        action.next_attempt_at = None
        action.save(update_fields=['attempts', 'next_attempt_at'])
        self._mark_action_result(action, 'SENT', f'SMS byla úspěšně odeslána na {target}{attempt_note}.')
        self._after_sms_final(action)
        return 'SENT'

    def _after_sms_final(self, action: OutgoingAction) -> None:
        """Po dokončení poslední SMS z ručního/hromadného odeslání, kde
        některé SMS zůstaly neodeslané, vyšle SYSTEM událost #SMS_FAILED
        (admin si na ni může navázat pravidlo s e-mailem/Teams)."""
        if action.status in ('PENDING', 'SENDING') or action.rule_id is not None or not action.event_log_id:
            return
        batch = OutgoingAction.objects.filter(event_log_id=action.event_log_id, action_type__in=SMS_ACTION_TYPES)
        if batch.filter(status__in=('PENDING', 'SENDING')).exists():
            return
        failed = batch.filter(status='FAILED').count()
        if not failed:
            return
        total = batch.count()
        try:
            fire_system_health_event(
                '#SMS_FAILED',
                f'Odeslání SMS (událost #{action.event_log_id}, uživatel {action.owner.username}) dokončeno: '
                f'{failed} z {total} SMS se nepodařilo odeslat. Poslat znovu lze na stránce průběhu odeslání: '
                f'{reverse("sms_batch_detail", args=[action.event_log_id])}',
            )
        except Exception:
            logger.exception('Nepodařilo se vyslat SYSTEM událost #SMS_FAILED')

    def _note_leftover_sms(self) -> None:
        """Odeslaná SMS zůstala v paměti modemu (smazání selhalo) - započítat
        do obsazenosti hned, ať pauza při zaplnění zabere ještě v tomhle
        cyklu. Samotnou SMS smaže sweep v příštím cyklu."""
        self._cycle_delete_failures += 1
        if self._storage_used is not None:
            self._storage_used += 1

    @staticmethod
    def _wants_delivery_report(action: OutgoingAction) -> bool:
        gateway = GatewaySettings.objects.filter(user=action.owner).first()
        return bool(gateway and gateway.delivery_reports)

    def _mark_action_result(self, action: OutgoingAction, status: str, detail: str) -> None:
        action.status = status
        action.execution_detail = detail
        action.processed_at = timezone.now()
        action.save(update_fields=['status', 'execution_detail', 'processed_at'])

    def _send_email_notification(self, action: OutgoingAction) -> None:
        recipients = self._get_email_recipients(action)
        if not recipients:
            raise ModemError('Není nastavený e-mail příjemce pro notifikaci.')

        source = action.event_log.source_number if action.event_log_id else 'unknown'
        event_type = action.event_log.event_type if action.event_log_id else 'EVENT'
        subject_prefix = getattr(settings, 'NOTIFY_EMAIL_SUBJECT_PREFIX', '[GSM Gate]')
        subject = f'{subject_prefix} {event_type} z {source}'

        send_mail(
            subject=subject,
            message=action.payload_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )

    def _send_teams_notification(self, action: OutgoingAction) -> None:
        webhook_url = self._get_teams_webhook(action)
        if not webhook_url:
            raise ModemError('Pro uživatele není nastavený Teams webhook URL.')

        source = action.event_log.source_number if action.event_log_id else 'unknown'
        event_type = action.event_log.event_type if action.event_log_id else 'EVENT'
        payload = {
            'text': f'[{event_type}] {source}\n\n{action.payload_message}',
        }
        body = json.dumps(payload).encode('utf-8')
        req = urllib_request.Request(
            webhook_url,
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib_request.urlopen(req, timeout=getattr(settings, 'NOTIFY_TEAMS_TIMEOUT', 8)):
            pass

    def _get_email_recipients(self, action: OutgoingAction) -> List[str]:
        recipients = set()

        if action.owner and action.owner.email:
            recipients.add(action.owner.email)

        if action.rule_id:
            for user in action.rule.users.exclude(email=''):
                recipients.add(user.email)

            for email in self._parse_rule_emails(action.rule.notification_emails):
                recipients.add(email)

            if action.rule.action == 'NOTIFY_NUM':
                for email in action.rule.target_numbers.filter(active=True).exclude(contact_email='').values_list('contact_email', flat=True):
                    recipients.add(email.strip().lower())
            elif action.rule.action == 'NOTIFY_GRP':
                for group in action.rule.target_groups.all():
                    for email in group.phone_numbers.filter(active=True).exclude(contact_email='').values_list('contact_email', flat=True):
                        recipients.add(email.strip().lower())

        return sorted(recipients)

    @staticmethod
    def _parse_rule_emails(raw_value: str) -> List[str]:
        if not raw_value:
            return []
        candidates = [item.strip().lower() for item in re.split(r'[\n,;]+', raw_value) if item.strip()]
        unique = []
        for email in candidates:
            if email not in unique:
                unique.append(email)
        return unique

    def _get_teams_webhook(self, action: OutgoingAction) -> str:
        gateway = GatewaySettings.objects.filter(user=action.owner).first()
        if gateway is None:
            return ''
        return (gateway.webhook_url or '').strip()

from dataclasses import dataclass
from datetime import timedelta
import json
import re
from typing import List
from urllib import request as urllib_request

from django.conf import settings
from django.core.mail import send_mail
from django.db import close_old_connections
from django.utils import timezone

from dashboard.models import OutgoingAction, GatewaySettings, SignalReading
from dashboard.services.rules_engine import process_incoming_event, normalize_phone_number
from dashboard.services.modem_manager import ModemManagerClient, ModemError

# Throttling pro SignalReading - i s výchozím 10s cyklem workeru by se bez
# tohohle historie nafoukla o desítky tisíc řádků denně. Výjimka: přechod
# (výpadek <-> obnovení) se zaznamená vždy, hned, ať ho graf nezmešká.
SIGNAL_HISTORY_MIN_INTERVAL = timedelta(minutes=5)

import logging

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    incoming_processed: int = 0
    outgoing_sent: int = 0
    outgoing_failed: int = 0


class GsmWorkerService:
    def __init__(self):
        self.client = ModemManagerClient(pin_code=self._get_configured_pin_code())

    @staticmethod
    def _get_configured_pin_code():
        settings_obj = GatewaySettings.objects.exclude(pin_code='').first()
        return settings_obj.pin_code if settings_obj else None

    def cycle(self) -> WorkerResult:
        close_old_connections()
        result = WorkerResult()

        try:
            self.client.connect()
        except ModemError:
            # I neúspěšné připojení je pro historii signálu důležité - bez
            # tohohle by výpadek modemu v Telemetrii nešel vůbec vidět
            # (cyklus by skončil dřív, než se k zápisu vůbec dostal).
            self._update_signal_quality()
            raise

        result.incoming_processed += self._process_incoming_sms()
        sent, failed = self._process_outgoing_actions()
        result.outgoing_sent += sent
        result.outgoing_failed += failed
        self._update_signal_quality()

        return result

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

    def _process_incoming_sms(self) -> int:
        messages = self.client.read_unread_sms()
        processed_count = 0

        for item in messages:
            source = normalize_phone_number(item.sender)
            settings_owner = GatewaySettings.objects.filter(allow_incoming_sms=True)

            for settings_obj in settings_owner:
                process_incoming_event(
                    user=settings_obj.user,
                    event_type='SMS',
                    source_number=source,
                    message_body=item.message,
                )

            try:
                self.client.delete_sms(item.index)
            except ModemError as e:
                logger.warning('Nepodařilo se smazat zpracovanou SMS (index %s): %s', item.index, e)
            processed_count += 1

        return processed_count

    def _process_outgoing_actions(self) -> List[int]:
        sent_count = 0
        failed_count = 0

        pending_actions = OutgoingAction.objects.filter(status='PENDING').order_by('created_at')[: settings.GSM_MAX_ACTIONS_PER_CYCLE]

        for action in pending_actions:
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

                target = normalize_phone_number(action.target_number)
                if not target:
                    raise ModemError('Neplatné cílové číslo')

                self.client.send_sms(
                    target,
                    action.payload_message,
                    request_delivery_report=self._wants_delivery_report(action),
                )
                self._mark_action_result(action, 'SENT', f'SMS byla úspěšně odeslána na {target}.')
                sent_count += 1
            except Exception as exc:
                self._mark_action_result(action, 'FAILED', f'Akce selhala: {exc}')
                failed_count += 1

        return sent_count, failed_count

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

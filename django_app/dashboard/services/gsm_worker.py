from dataclasses import dataclass
import json
import re
from typing import List
from urllib import request as urllib_request

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from dashboard.models import OutgoingAction, GatewaySettings
from dashboard.services.rules_engine import process_incoming_event, normalize_phone_number
from dashboard.services.sim7000 import Sim7000Client, ModemError


@dataclass
class WorkerResult:
    incoming_processed: int = 0
    outgoing_sent: int = 0
    outgoing_failed: int = 0


class GsmWorkerService:
    def __init__(self):
        self.client = Sim7000Client(
            port=settings.GSM_MODEM_PORT,
            baudrate=settings.GSM_MODEM_BAUD,
            timeout=settings.GSM_MODEM_TIMEOUT,
        )

    def cycle(self) -> WorkerResult:
        result = WorkerResult()
        self.client.connect()

        result.incoming_processed += self._process_incoming_sms()
        sent, failed = self._process_outgoing_actions()
        result.outgoing_sent += sent
        result.outgoing_failed += failed

        return result

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

            self.client.delete_sms(item.index)
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

                self.client.send_sms(target, action.payload_message)
                self._mark_action_result(action, 'SENT', f'SMS byla úspěšně odeslána na {target}.')
                sent_count += 1
            except Exception as exc:
                self._mark_action_result(action, 'FAILED', f'Akce selhala: {exc}')
                failed_count += 1

        return sent_count, failed_count

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

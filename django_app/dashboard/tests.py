from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import AutomationRule, DeviceObject, PhoneNumber


class RuleCreateFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username='rule-admin',
            email='rule-admin@example.com',
            password='test-pass-123',
        )
        self.client.force_login(self.user)

        self.source_number = PhoneNumber.objects.create(
            owner=self.user,
            number='+420777000111',
            description='Zdroj',
            contact_email='source@example.com',
            active=True,
        )
        self.source_number.users.add(self.user)

        self.target_number = PhoneNumber.objects.create(
            owner=self.user,
            number='+420777000222',
            description='Cil',
            contact_email='target@example.com',
            active=True,
        )
        self.target_number.users.add(self.user)

        self.source_object = DeviceObject.objects.create(
            owner=self.user,
            name='Objekt API',
            object_label='Senzor dveri',
            object_type='SENSOR',
            icon='hdd-network',
            active=True,
            status_flag='OK',
        )

    def test_rule_create_accepts_step2_exact_source_choice_with_api_object(self):
        response = self.client.post(
            reverse('rule_add'),
            data={
                'name': 'Pravidlo test krok 2',
                'description': 'Kontrola pruchodu krokem 2',
                'active': 'on',
                'priority': '10',
                'event_type': 'SMS_API',
                'match_type': 'EXACT',
                'source_number': '',
                'source_number_choice': self.source_number.number,
                'source_groups': [],
                'source_objects': [str(self.source_object.pk)],
                'use_message_flag': '',
                'message_flag': '',
                'action': 'NOTIFY_NUM',
                'target_numbers': [str(self.target_number.pk)],
                'target_groups': [],
                'forward_to_number': '',
                'notify_via_sms': 'on',
                'notify_via_email': '',
                'notify_via_teams': '',
                'notification_email_choices': [],
                'notification_emails': '',
                'include_original_message': 'on',
                'custom_message': 'Test notifikace',
                'stop_processing': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('rules_list'))

        rule = AutomationRule.objects.get(name='Pravidlo test krok 2')
        self.assertEqual(rule.source_number, self.source_number.number)
        self.assertEqual(rule.event_type, 'SMS_API')
        self.assertEqual(rule.match_type, 'EXACT')
        self.assertEqual(rule.action, 'NOTIFY_NUM')
        self.assertTrue(rule.notify_via_sms)
        self.assertFalse(rule.notify_via_email)
        self.assertTrue(rule.source_objects.filter(pk=self.source_object.pk).exists())
        self.assertTrue(rule.target_numbers.filter(pk=self.target_number.pk).exists())


# --- Ochrana paměti SMS v modemu a fronty (incident 2026-11) ---------------

from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from .models import IncomingEventLog, OutgoingAction, SystemState
from .services import modem_manager
from .services.gsm_worker import GsmWorkerService
from .services.modem_manager import ModemError, ModemManagerClient, ModemSms, StorageInfo, parse_cpms
from .services.selftest import check_modem_storage


class FakeModemClient:
    """Náhrada ModemManagerClient pro testy workeru - drží SMS v paměti."""

    validate_sms = staticmethod(ModemManagerClient.validate_sms)

    def __init__(self, messages=None, fail_send=False, fail_delete=False, storage_info=None, fail_numbers=()):
        self.messages = {m.index: m for m in (messages or [])}
        self.fail_send = fail_send
        self.fail_numbers = set(fail_numbers)
        self.fail_delete = fail_delete
        self.storage_info = storage_info
        self.sent = []

    def connect(self):
        pass

    def close(self):
        pass

    def get_signal_quality(self):
        return 70

    def list_sms(self):
        return list(self.messages.values())

    def delete_sms(self, index):
        if self.fail_delete:
            raise ModemError('delete selhal')
        self.messages.pop(index, None)

    def get_storage_info(self):
        return self.storage_info

    def send_sms(self, number, text, request_delivery_report=False):
        if self.fail_send or number in self.fail_numbers:
            exc = ModemError('send selhal')
            exc.sms_cleaned = True
            raise exc
        self.sent.append((number, text))
        return True


@override_settings(
    GSM_MAX_ACTIONS_PER_CYCLE=30,
    GSM_MAX_MANUAL_SMS_PER_CYCLE=10,
    GSM_MODEM_SMS_CAPACITY=20,
    GSM_MODEM_STORAGE_PAUSE_PERCENT=80,
    GSM_SMS_FAILURE_BREAKER=3,
)
class ModemStorageProtectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='op', password='x')
        self.event_log = IncomingEventLog.objects.create(owner=self.user, event_type='SYSTEM', source_number='')
        self.rule = AutomationRule.objects.create(owner=self.user, name='Pravidlo')

    def _worker(self, client):
        worker = GsmWorkerService()
        worker.client = client
        return worker

    def _action(self, target='+420777000111', rule=None, action_type='NOTIFY_SMS', text='Ahoj'):
        return OutgoingAction.objects.create(
            owner=self.user, event_log=self.event_log, rule=rule, action_type=action_type,
            target_number=target, payload_message=text, status='PENDING',
        )

    # --- úklid paměti ---

    def test_sweep_deletes_sent_leftovers_and_records_storage(self):
        client = FakeModemClient([ModemSms(index=i, state='sent', number='737696288') for i in range(12)])
        result = self._worker(client).cycle()

        self.assertEqual(client.messages, {})
        self.assertEqual(result.modem_sms_deleted, 12)
        state = SystemState.load()
        self.assertEqual(state.modem_sms_used, 0)
        self.assertEqual(state.modem_sms_capacity, 20)
        self.assertEqual(state.modem_sms_capacity_source, 'CONFIG')
        self.assertIsNotNone(state.modem_sms_checked_at)

    def test_received_sms_is_processed_and_deleted(self):
        client = FakeModemClient([ModemSms(index=5, state='received', number='+420777000999', text='test')])
        result = self._worker(client).cycle()

        self.assertEqual(result.incoming_processed, 1)
        self.assertEqual(client.messages, {})

    def test_receiving_is_kept_until_timeout(self):
        client = FakeModemClient([ModemSms(index=7, state='receiving')])
        worker = self._worker(client)
        worker.cycle()
        self.assertIn(7, client.messages)

        worker._first_seen_transient[7] = timezone.now() - timedelta(minutes=31)
        worker.cycle()
        self.assertNotIn(7, client.messages)

    def test_failed_delete_is_reported(self):
        client = FakeModemClient([ModemSms(index=1, state='sent')], fail_delete=True)
        self._worker(client).cycle()

        state = SystemState.load()
        self.assertEqual(state.modem_sms_used, 1)
        self.assertEqual(state.modem_sms_delete_failures, 1)
        self.assertEqual(state.modem_sms_states, {'sent': 1})

    def test_cpms_values_take_precedence(self):
        client = FakeModemClient(storage_info=StorageInfo(storage='me', used=3, total=50))
        self._worker(client).cycle()

        state = SystemState.load()
        self.assertEqual((state.modem_sms_used, state.modem_sms_capacity), (3, 50))
        self.assertEqual(state.modem_sms_capacity_source, 'AT')

    # --- fronta ---

    def test_full_storage_pauses_sms_but_not_other_actions(self):
        # 17 zbytků, které nejdou smazat = 85 % z 20 -> nad prahem 80 %.
        client = FakeModemClient([ModemSms(index=i, state='sent') for i in range(17)], fail_delete=True)
        sms = self._action()
        pull = self._action(action_type='DEVICE_PULL', target='OBJ')

        result = self._worker(client).cycle()

        sms.refresh_from_db()
        pull.refresh_from_db()
        self.assertEqual(sms.status, 'PENDING')
        self.assertEqual(pull.status, 'SENT')
        self.assertEqual(result.outgoing_deferred, 1)
        self.assertEqual(client.sent, [])
        self.assertIn('zaplněná', SystemState.load().sms_sending_paused_reason)

    def test_invalid_message_rejected_before_modem(self):
        client = FakeModemClient()
        bad_number = self._action(target='abc')
        apostrophe = self._action(text="it's")

        self._worker(client).cycle()

        for action in (bad_number, apostrophe):
            action.refresh_from_db()
            self.assertEqual(action.status, 'FAILED')
            self.assertIn('do modemu se nic nezapsalo', action.execution_detail)
        self.assertEqual(client.sent, [])

    def test_breaker_stops_sending_after_consecutive_failures(self):
        client = FakeModemClient(fail_send=True)
        actions = [self._action(target=f'+42077700{i:04d}') for i in range(8)]

        worker = self._worker(client)
        result = worker.cycle()

        refreshed = [OutgoingAction.objects.get(pk=a.pk) for a in actions]
        # 3 zkoušené -> zpět do fronty k opakování, 5 vůbec nezkoušených.
        self.assertEqual(sum(1 for a in refreshed if a.attempts == 1 and a.next_attempt_at), 3)
        self.assertTrue(all(a.status == 'PENDING' for a in refreshed))
        self.assertEqual(result.outgoing_deferred, 5)
        self.assertIn('pozastaveno', SystemState.load().sms_sending_paused_reason)

        # Další cyklus během cooldownu nic neodesílá.
        result = worker.cycle()
        self.assertEqual(result.outgoing_failed, 0)
        self.assertEqual(result.outgoing_deferred, 5)

    def test_rule_actions_go_first_and_manual_is_capped(self):
        client = FakeModemClient()
        manual = [self._action(target=f'+42060000{i:04d}') for i in range(15)]
        rule_action = self._action(target='+420777999999', rule=self.rule)

        self._worker(client).cycle()

        self.assertEqual(client.sent[0][0], '+420777999999')
        rule_action.refresh_from_db()
        self.assertEqual(rule_action.status, 'SENT')
        self.assertEqual(len(client.sent), 1 + 10)
        self.assertEqual(OutgoingAction.objects.filter(pk__in=[a.pk for a in manual], status='PENDING').count(), 5)

    # --- ukazatel / sebediagnostika ---

    def test_check_modem_storage_levels(self):
        state = SystemState.load()
        state.modem_sms_capacity = 20
        state.modem_sms_checked_at = timezone.now()
        for used, expected in ((2, 'OK'), (11, 'WARN'), (17, 'ERROR')):
            state.modem_sms_used = used
            state.save()
            self.assertEqual(check_modem_storage()['status'], expected, used)

    def test_gateway_status_shows_storage_panel(self):
        admin = get_user_model().objects.create_superuser(username='adm', password='x', email='a@example.com')
        self.client.force_login(admin)
        state = SystemState.load()
        state.modem_sms_used, state.modem_sms_capacity, state.modem_sms_checked_at = 5, 20, timezone.now()
        state.save()

        response = self.client.get(reverse('gateway_status'))
        self.assertContains(response, 'Paměť SMS v modemu')
        self.assertContains(response, '5 / 20 SMS')

        data = self.client.get(reverse('gateway_signal_api')).json()
        self.assertEqual(data['storage']['percent'], 25)


@override_settings(
    GSM_MAX_ACTIONS_PER_CYCLE=30,
    GSM_MAX_MANUAL_SMS_PER_CYCLE=10,
    GSM_MODEM_SMS_CAPACITY=20,
    GSM_MODEM_STORAGE_PAUSE_PERCENT=80,
    GSM_SMS_FAILURE_BREAKER=3,
)
class SmsDispatchTests(TestCase):
    GATEWAY = '+420737696288'

    def setUp(self):
        from .models import GatewaySettings

        self.admin = get_user_model().objects.create_superuser(username='adm', password='x', email='a@example.com')
        GatewaySettings.objects.create(user=self.admin, own_number='737 696 288')
        self.event_log = IncomingEventLog.objects.create(owner=self.admin, event_type='SYSTEM', source_number='')

    def _worker(self, client):
        worker = GsmWorkerService()
        worker.client = client
        return worker

    def _action(self, target, **kwargs):
        return OutgoingAction.objects.create(
            owner=self.admin, event_log=self.event_log, action_type='NOTIFY_SMS',
            target_number=target, payload_message='Evakuace', status='PENDING', **kwargs,
        )

    # --- číslo brány ---

    def test_canonical_number_variants(self):
        from .services.sms_dispatch import canonical_number

        for raw in ('737696288', '+420737696288', '00420737696288', '420 737 696 288'):
            self.assertEqual(canonical_number(raw), self.GATEWAY, raw)

    def test_plan_recipients_excludes_gateway_invalid_and_duplicates(self):
        from .services.sms_dispatch import plan_recipients

        plan = plan_recipients(['+420777000111', '737696288', 'abc', '777000111', '+420777000222'])
        self.assertEqual(plan.valid, ['+420777000111', '+420777000222'])
        self.assertEqual(plan.gateway, ['737696288'])
        self.assertEqual(plan.invalid, ['abc'])
        self.assertEqual(plan.duplicates, ['777000111'])

    def test_worker_never_sends_to_gateway_number(self):
        client = FakeModemClient()
        action = self._action('+420737696288')
        self._worker(client).cycle()

        action.refresh_from_db()
        self.assertEqual(action.status, 'FAILED')
        self.assertIn('číslo samotné brány', action.execution_detail)
        self.assertEqual(client.sent, [])

    def test_incoming_from_gateway_number_is_ignored(self):
        from .services.rules_engine import process_incoming_event

        AutomationRule.objects.create(
            owner=self.admin, name='Vše', match_type='ANY', event_type='SMS', action='NOTIFY_NUM', notify_via_sms=True,
        )
        log, matched, queued = process_incoming_event(self.admin, 'SMS', '+420737696288', 'Evakuace')
        self.assertEqual((matched, queued), (0, 0))
        self.assertIn('vlastního čísla brány', log.result_summary)

    # --- ochrana proti smyčce (ping-pong) ---

    def _self_forward_rule(self, number='+420737000111'):
        me = PhoneNumber.objects.create(owner=self.admin, number=number, active=True)
        rule = AutomationRule.objects.create(
            owner=self.admin, name='Vše na mě', match_type='ANY', event_type='SMS', action='FORWARD',
        )
        rule.target_numbers.add(me)
        return rule

    def test_self_forward_works_for_repeated_human_messages(self):
        """Případ z provozu: pravidlo „přesměruj všechno na moje číslo“ a SMS
        z vlastního telefonu - každá zpráva se přepošle, žádná se nezahodí."""
        from .services.rules_engine import process_incoming_event

        rule = self._self_forward_rule()
        for text in ('Test 1', 'Test 2'):
            process_incoming_event(self.admin, 'SMS', '+420737000111', text)
        self.assertEqual(OutgoingAction.objects.filter(rule=rule).count(), 2)

    def test_pingpong_stops_sms_back_after_max_rounds_and_alerts_once(self):
        from .services.rules_engine import process_incoming_event
        from .services.sms_dispatch import PINGPONG_MAX_ROUNDS

        rule = self._self_forward_rule()
        other = PhoneNumber.objects.create(owner=self.admin, number='+420777888999', active=True)
        rule.target_numbers.add(other)

        for i in range(PINGPONG_MAX_ROUNDS + 2):
            log, _, _ = process_incoming_event(self.admin, 'SMS', '+420737000111', f'Auto-odpověď {i}')

        to_source = OutgoingAction.objects.filter(rule=rule, target_number='+420737000111').count()
        to_other = OutgoingAction.objects.filter(rule=rule, target_number='+420777888999').count()
        self.assertEqual(to_source, PINGPONG_MAX_ROUNDS)
        self.assertEqual(to_other, PINGPONG_MAX_ROUNDS + 2)
        self.assertIn('pravděpodobná smyčka', log.result_summary)
        loop_alerts = IncomingEventLog.objects.filter(event_type='SYSTEM', message_body__contains='#SMS_LOOP')
        self.assertEqual(loop_alerts.count(), 1)

    # --- souběh workerů ---

    def test_claimed_action_is_not_sent_twice(self):
        """Druhá instance workeru nesmí poslat akci, kterou už zabrala první."""
        action = self._action('+420777000001')
        OutgoingAction.objects.filter(pk=action.pk).update(status='SENDING', processed_at=timezone.now())

        client = FakeModemClient()
        worker = self._worker(client)
        stale_copy = OutgoingAction.objects.get(pk=action.pk)
        stale_copy.status = 'PENDING'  # jak ji viděl worker při výběru z fronty
        self.assertFalse(worker._claim(stale_copy))
        worker.cycle()
        self.assertEqual(client.sent, [])

    def test_interrupted_send_becomes_uncertain_not_retried(self):
        action = self._action('+420777000001')
        OutgoingAction.objects.filter(pk=action.pk).update(
            status='SENDING', processed_at=timezone.now() - timedelta(minutes=20),
        )
        client = FakeModemClient()
        self._worker(client).cycle()

        action.refresh_from_db()
        self.assertEqual(action.status, 'FAILED')
        self.assertIn('Nejisté', action.execution_detail)
        self.assertEqual(client.sent, [])

    # --- opakování ---

    def test_failed_sms_is_retried_later_without_blocking_others(self):
        client = FakeModemClient(fail_numbers={'+420777000001'})
        bad = self._action('+420777000001')
        good = [self._action(f'+42077700100{i}') for i in range(3)]
        worker = self._worker(client)

        worker.cycle()
        bad.refresh_from_db()
        self.assertEqual((bad.status, bad.attempts), ('PENDING', 1))
        self.assertGreater(bad.next_attempt_at, timezone.now())
        self.assertEqual(OutgoingAction.objects.filter(pk__in=[g.pk for g in good], status='SENT').count(), 3)

        # Další cyklus před uplynutím odstupu se na ni nesahá.
        worker.cycle()
        bad.refresh_from_db()
        self.assertEqual(bad.attempts, 1)

    def test_retries_exhausted_then_failed_and_notified(self):
        from .services.sms_dispatch import MAX_ATTEMPTS

        client = FakeModemClient(fail_numbers={'+420777000001'})
        bad = self._action('+420777000001')
        worker = self._worker(client)
        for _ in range(MAX_ATTEMPTS):
            OutgoingAction.objects.filter(pk=bad.pk).update(next_attempt_at=None)
            worker._sms_paused_until = None
            worker.cycle()

        bad.refresh_from_db()
        self.assertEqual((bad.status, bad.attempts), ('FAILED', MAX_ATTEMPTS))
        self.assertIn('Lze odeslat znovu', bad.execution_detail)
        self.assertTrue(IncomingEventLog.objects.filter(event_type='SYSTEM', message_body__contains='#SMS_FAILED').exists())

    def test_retry_is_queued_behind_untried_messages(self):
        client = FakeModemClient()
        # Původně první ve frontě, selhala a dostala odstup; mezitím čeká
        # nezkoušená SMS zařazená dřív, než na opakování přišla řada.
        retry = self._action('+420777000001', attempts=1, next_attempt_at=timezone.now() - timedelta(seconds=1))
        OutgoingAction.objects.filter(pk=retry.pk).update(created_at=timezone.now() - timedelta(hours=1))
        fresh = self._action('+420777000002')
        OutgoingAction.objects.filter(pk=fresh.pk).update(created_at=timezone.now() - timedelta(minutes=10))

        self._worker(client).cycle()
        self.assertEqual([n for n, _ in client.sent], ['+420777000002', '+420777000001'])
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, 'SENT')

    def test_worker_reports_more_work_for_large_batch(self):
        client = FakeModemClient()
        for i in range(25):
            self._action(f'+4207770002{i:02d}')
        result = self._worker(client).cycle()
        self.assertEqual(len(client.sent), 10)
        self.assertTrue(result.more_work)

    # --- UI ---

    def test_send_view_previews_then_queues(self):
        self.client.force_login(self.admin)
        data = {'message': 'Evakuace budovy A', 'manual_numbers': '+420777000111\n737696288\n+420777000111'}

        response = self.client.post(reverse('send_sms'), data)
        self.assertContains(response, 'Potvrdit odeslání SMS')
        self.assertContains(response, 'Číslo brány')
        self.assertFalse(OutgoingAction.objects.filter(payload_message='Evakuace budovy A').exists())

        response = self.client.post(reverse('send_sms'), {**data, 'confirm': '1'})
        queued = OutgoingAction.objects.filter(payload_message='Evakuace budovy A')
        self.assertEqual(list(queued.values_list('target_number', flat=True)), ['+420777000111'])
        self.assertRedirects(response, reverse('sms_batch_detail', args=[queued.first().event_log_id]))

    def test_batch_resend_and_cancel(self):
        self.client.force_login(self.admin)
        failed = self._action('+420777000001')
        OutgoingAction.objects.filter(pk=failed.pk).update(status='FAILED', attempts=4)
        waiting = self._action('+420777000002')

        page = self.client.get(reverse('sms_batch_detail', args=[self.event_log.pk]))
        self.assertContains(page, 'Poslat znovu')

        self.client.post(reverse('sms_batch_cancel', args=[self.event_log.pk]))
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, 'CANCELLED')

        self.client.post(reverse('sms_batch_resend', args=[self.event_log.pk]), {'action_id': failed.pk})
        failed.refresh_from_db()
        self.assertEqual((failed.status, failed.attempts), ('PENDING', 0))


class ModemManagerClientTests(TestCase):
    def test_parse_cpms_uses_receive_storage(self):
        info = parse_cpms('response: \'+CPMS: "SM",1,30,"SM",1,30,"ME",12,25\'')
        self.assertEqual((info.storage, info.used, info.total), ('me', 12, 25))
        self.assertIsNone(parse_cpms('error: command only available in debug mode'))

    def test_send_failure_still_deletes_created_sms(self):
        calls = []

        def fake_mmcli(args, timeout=20.0):
            calls.append(args)
            if any(a.startswith('--messaging-create-sms') for a in args):
                return {'modem': {'messaging': {'created-sms': '/org/freedesktop/ModemManager1/SMS/42'}}}
            if '--send' in args:
                raise ModemError('timeout')
            return {}

        client = ModemManagerClient(modem_index=1)
        with mock.patch.object(modem_manager, '_run_mmcli', side_effect=fake_mmcli):
            with self.assertRaises(ModemError) as ctx:
                client.send_sms('+420777000111', 'Ahoj')

        self.assertTrue(ctx.exception.sms_cleaned)
        self.assertIn('--messaging-delete-sms=/org/freedesktop/ModemManager1/SMS/42', calls[-1])

    def test_invalid_input_never_reaches_modem(self):
        client = ModemManagerClient(modem_index=1)
        with mock.patch.object(modem_manager, '_run_mmcli') as run:
            for number, text in (('abc', 'x'), ('+420777000111', ''), ('+420777000111', "it's"), ('+420777000111', 'ř' * 700)):
                with self.assertRaises(ModemError):
                    client.send_sms(number, text)
        run.assert_not_called()

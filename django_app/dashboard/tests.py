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

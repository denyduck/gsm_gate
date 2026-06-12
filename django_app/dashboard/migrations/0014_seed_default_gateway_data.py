from django.db import migrations


def seed_default_gateway_data(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Group = apps.get_model('dashboard', 'Group')
    PhoneNumber = apps.get_model('dashboard', 'PhoneNumber')
    GatewaySettings = apps.get_model('dashboard', 'GatewaySettings')
    AutomationRule = apps.get_model('dashboard', 'AutomationRule')
    IncomingEventLog = apps.get_model('dashboard', 'IncomingEventLog')
    OutgoingAction = apps.get_model('dashboard', 'OutgoingAction')

    for user in User.objects.filter(is_active=True):
        GatewaySettings.objects.get_or_create(
            user=user,
            defaults={
                'serial_port': '/dev/ttyUSB0',
                'baud_rate': 115200,
                'network_mode': 'AUTO',
                'sms_storage': 'SIM',
                'delivery_reports': True,
                'allow_incoming_sms': True,
                'auto_start_gateway': True,
                'heartbeat_interval_sec': 60,
            },
        )

        vip_group, _ = Group.objects.get_or_create(
            name='Výchozí: VIP zákazníci',
            defaults={'description': 'Výchozí skupina pro prioritní čísla.'},
        )
        team_group, _ = Group.objects.get_or_create(
            name='Výchozí: Interní tým',
            defaults={'description': 'Výchozí interní notifikační skupina.'},
        )
        service_group, _ = Group.objects.get_or_create(
            name='Výchozí: Servisní kontakt',
            defaults={'description': 'Výchozí servisní a eskalační kontakt.'},
        )

        vip_group.users.add(user)
        team_group.users.add(user)
        service_group.users.add(user)

        vip_number, _ = PhoneNumber.objects.get_or_create(
            owner=user,
            number='+420777100100',
            defaults={'description': 'Výchozí: VIP klient', 'active': True},
        )
        team_number, _ = PhoneNumber.objects.get_or_create(
            owner=user,
            number='+420777200200',
            defaults={'description': 'Výchozí: Interní notifikace', 'active': True},
        )
        service_number, _ = PhoneNumber.objects.get_or_create(
            owner=user,
            number='+420777300300',
            defaults={'description': 'Výchozí: Servisní kontakt', 'active': True},
        )

        for phone in (vip_number, team_number, service_number):
            phone.users.add(user)

        vip_number.groups.add(vip_group)
        team_number.groups.add(team_group)
        service_number.groups.add(service_group)

        rule_notify_vip, created_notify = AutomationRule.objects.get_or_create(
            owner=user,
            name='Výchozí: VIP notifikace internímu týmu',
            defaults={
                'description': 'Při zprávě z VIP skupiny odešli notifikaci internímu týmu.',
                'active': True,
                'priority': 10,
                'event_type': 'SMS',
                'match_type': 'GROUP',
                'source_group': vip_group,
                'action': 'NOTIFY',
                'include_original_message': True,
                'custom_message': 'Výchozí: VIP událost na bráně.',
                'stop_processing': True,
            },
        )
        if created_notify:
            rule_notify_vip.target_groups.add(team_group)

        rule_forward_any, _ = AutomationRule.objects.get_or_create(
            owner=user,
            name='Výchozí: Přeposlat obecné SMS na servis',
            defaults={
                'description': 'Obecné SMS přeposlat na servisní číslo.',
                'active': True,
                'priority': 50,
                'event_type': 'SMS',
                'match_type': 'ANY',
                'action': 'FORWARD',
                'forward_to_number': service_number.number,
                'include_original_message': True,
                'custom_message': 'Výchozí: Přeposílám příchozí SMS.',
                'stop_processing': False,
            },
        )

        if not IncomingEventLog.objects.filter(owner=user).exists():
            event_log = IncomingEventLog.objects.create(
                owner=user,
                event_type='SMS',
                source_number=vip_number.number,
                message_body='Výchozí testovací zpráva z VIP čísla.',
                processed=True,
                result_summary='Výchozí inicializační log: vytvořené akce byly připraveny.',
            )

            OutgoingAction.objects.create(
                owner=user,
                event_log=event_log,
                rule=rule_notify_vip,
                action_type='NOTIFY_SMS',
                target_number=team_number.number,
                payload_message='Výchozí notifikace: VIP událost.',
                status='SENT',
            )

            OutgoingAction.objects.create(
                owner=user,
                event_log=event_log,
                rule=rule_forward_any,
                action_type='FORWARD_INFO',
                target_number=service_number.number,
                payload_message='Výchozí přeposlání: zpráva čeká na odeslání.',
                status='PENDING',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0013_granular_roles_for_rules_actions'),
    ]

    operations = [
        migrations.RunPython(seed_default_gateway_data, migrations.RunPython.noop),
    ]

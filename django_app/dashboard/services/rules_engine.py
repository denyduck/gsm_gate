from django.db.models import Q

from dashboard.models import AutomationRule, IncomingEventLog, OutgoingAction


def normalize_phone_number(raw_number):
    text = (raw_number or '').strip()
    return ''.join(ch for ch in text if ch.isdigit() or ch == '+')


def rule_log_label(rule):
    if rule.use_message_flag and rule.message_flag:
        return f'{rule.name} [příznak: {rule.message_flag}]'
    return rule.name


def event_type_matches(rule_event_type, incoming_event_type):
    normalized_rule_type = (rule_event_type or '').upper()
    normalized_incoming_type = (incoming_event_type or '').upper()

    mapping = {
        'SMS': {'SMS'},
        'CALL': {'CALL'},
        'API': {'API'},
        'SMS_CALL': {'SMS', 'CALL'},
        'SMS_API': {'SMS', 'API'},
        'CALL_API': {'CALL', 'API'},
        'ANY': {'SMS', 'CALL'},
        'ALL': {'SMS', 'CALL', 'API'},
    }

    allowed_types = mapping.get(normalized_rule_type, {normalized_rule_type})
    return normalized_incoming_type in allowed_types


def rule_matches_event(rule, event_type, source_number, message_body='', source_device_object=None):
    normalized_source = normalize_phone_number(source_number)
    normalized_message = (message_body or '').strip().lower()
    normalized_event_type = (event_type or '').upper()

    if not event_type_matches(rule.event_type, event_type):
        return False

    if normalized_event_type == 'API' and rule.source_objects.exists():
        if source_device_object is None:
            return False
        if not rule.source_objects.filter(pk=source_device_object.pk).exists():
            return False

    if rule.use_message_flag:
        required_flag = (rule.message_flag or '').strip().lower()
        if not required_flag:
            return False
        if required_flag not in normalized_message:
            return False

    if rule.match_type == 'ANY':
        return True

    if rule.match_type == 'EXACT':
        return normalized_source == normalize_phone_number(rule.source_number)

    if rule.match_type == 'GROUP':
        source_groups = list(rule.source_groups.all())
        if not source_groups and rule.source_group_id:
            source_groups = [rule.source_group]

        for group in source_groups:
            for phone in group.phone_numbers.filter(active=True):
                if normalize_phone_number(phone.number) == normalized_source:
                    return True

    return False


def collect_target_numbers(rule):
    target_set = set()

    for phone in rule.target_numbers.filter(active=True):
        normalized = normalize_phone_number(phone.number)
        if normalized:
            target_set.add(normalized)

    for group in rule.target_groups.all():
        for phone in group.phone_numbers.filter(active=True):
            normalized = normalize_phone_number(phone.number)
            if normalized:
                target_set.add(normalized)

    return sorted(target_set)


def process_incoming_event(user, event_type, source_number, message_body, source_device_object=None):
    event_log = IncomingEventLog.objects.create(
        owner=user,
        event_type=event_type,
        source_number=normalize_phone_number(source_number),
        message_body=message_body or '',
    )

    summaries = []
    matched_count = 0
    queued_count = 0

    rules = AutomationRule.objects.filter(active=True).filter(
        Q(owner=user) | Q(users=user)
    ).distinct().order_by('priority', 'id')

    for rule in rules:
        if not rule_matches_event(rule, event_type, source_number, message_body, source_device_object=source_device_object):
            continue

        matched_count += 1
        log_rule_name = rule_log_label(rule)

        if rule.action == 'IGNORE':
            summaries.append(f'Pravidlo "{log_rule_name}": událost ignorována.')

        elif rule.action in ('NOTIFY_NUM', 'NOTIFY_GRP'):
            if rule.action == 'NOTIFY_NUM':
                targets = []
                for phone in rule.target_numbers.filter(active=True):
                    normalized = normalize_phone_number(phone.number)
                    if normalized:
                        targets.append(normalized)
                targets = sorted(set(targets))
            else:
                targets = []
                for group in rule.target_groups.all():
                    for phone in group.phone_numbers.filter(active=True):
                        normalized = normalize_phone_number(phone.number)
                        if normalized:
                            targets.append(normalized)
                targets = sorted(set(targets))

            payload = rule.custom_message.strip() if rule.custom_message else ''
            if not payload:
                payload = f'[{event_type}] událost z čísla {normalize_phone_number(source_number)}'

            if rule.include_original_message and message_body:
                payload = f'{payload}\nObsah: {message_body}'

            selected_channels = []
            if rule.notify_via_sms:
                selected_channels.append('SMS')
            if rule.notify_via_email:
                selected_channels.append('e-mail')
            if rule.notify_via_teams:
                selected_channels.append('Teams')

            if not selected_channels:
                summaries.append(f'Pravidlo "{log_rule_name}": není vybraný žádný notifikační kanál.')
                if rule.stop_processing:
                    summaries.append('Zpracování ukončeno podle priority pravidel.')
                    break
                continue

            rule_queued_count = 0

            if rule.notify_via_sms:
                if not targets:
                    summaries.append(f'Pravidlo "{log_rule_name}": kanál SMS přeskočen, protože chybí cílová čísla/skupiny.')
                else:
                    for target in targets:
                        OutgoingAction.objects.create(
                            owner=user,
                            event_log=event_log,
                            rule=rule,
                            action_type='NOTIFY_SMS',
                            target_number=target,
                            payload_message=payload,
                            status='PENDING',
                        )
                        queued_count += 1
                        rule_queued_count += 1

            if rule.notify_via_email:
                OutgoingAction.objects.create(
                    owner=user,
                    event_log=event_log,
                    rule=rule,
                    action_type='NOTIFY_EMAIL',
                    target_number='MAIL',
                    payload_message=payload,
                    status='PENDING',
                )
                queued_count += 1
                rule_queued_count += 1

            if rule.notify_via_teams:
                OutgoingAction.objects.create(
                    owner=user,
                    event_log=event_log,
                    rule=rule,
                    action_type='NOTIFY_TEAMS',
                    target_number='TEAMS',
                    payload_message=payload,
                    status='PENDING',
                )
                queued_count += 1
                rule_queued_count += 1

            if rule_queued_count > 0:
                summaries.append(
                    f'Pravidlo "{log_rule_name}": zařazeno {rule_queued_count} akcí pro kanály {", ".join(selected_channels)}.'
                )
            else:
                summaries.append(f'Pravidlo "{log_rule_name}": nebyla zařazena žádná odchozí akce.')

        elif rule.action == 'FORWARD':
            targets = []
            for phone in rule.target_numbers.filter(active=True):
                normalized = normalize_phone_number(phone.number)
                if normalized:
                    targets.append(normalized)
            targets = sorted(set(targets))

            if not targets:
                legacy_target = normalize_phone_number(rule.forward_to_number)
                if legacy_target:
                    targets = [legacy_target]

            if not targets:
                summaries.append(f'Pravidlo "{log_rule_name}": chybí cílové číslo pro akci „Předat na číslo“.')
            else:
                payload = rule.custom_message.strip() if rule.custom_message else ''
                if not payload:
                    payload = f'[{event_type}] předání na číslo z čísla {normalize_phone_number(source_number)}'

                if rule.include_original_message and message_body:
                    payload = f'{payload}\nObsah: {message_body}'

                for target in targets:
                    OutgoingAction.objects.create(
                        owner=user,
                        event_log=event_log,
                        rule=rule,
                        action_type='FORWARD_INFO',
                        target_number=target,
                        payload_message=payload,
                        status='PENDING',
                    )
                    queued_count += 1

                summaries.append(
                    f'Pravidlo "{log_rule_name}": akce „Předat na číslo“ zařazena do fronty pro {len(targets)} cílových čísel.'
                )

        if rule.stop_processing:
            summaries.append('Zpracování ukončeno podle priority pravidel.')
            break

    if matched_count == 0:
        summaries.append('Nebyla nalezena žádná aktivní pravidla pro tuto událost.')

    event_log.processed = True
    event_log.result_summary = '\n'.join(summaries)
    event_log.save(update_fields=['processed', 'result_summary'])

    return event_log, matched_count, queued_count

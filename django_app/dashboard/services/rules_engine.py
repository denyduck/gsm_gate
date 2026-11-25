import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from dashboard.models import AutomationRule, BlockedNumber, IncomingEventLog, OutgoingAction, SecurityRule

logger = logging.getLogger(__name__)


def normalize_phone_number(raw_number):
    text = (raw_number or '').strip()
    return ''.join(ch for ch in text if ch.isdigit() or ch == '+')


def get_security_rule(user):
    """Vrátí (a při prvním použití založí) pevné bezpečnostní pravidlo uživatele."""
    rule, _ = SecurityRule.objects.get_or_create(owner=user)
    return rule


# Ochrana proti smyčce odchozích akcí (jedno pravidlo opakovaně bombarduje
# stejný cíl) - nezávislá na příčině (doručenka mylně vykázaná jako nová SMS,
# auto-odpověď na straně příjemce, budoucí neznámý bug apod.). Reálný incident
# 2026-09-11 (viz docs/modem-diagnostika.md) vygeneroval desítky odchozích SMS
# na stejné číslo během pár minut, než zasáhla obecná bezpečnostní blokace
# zdrojového čísla - tohle je rychlejší, cílenější pojistka na úrovni
# konkrétního pravidla a cíle.
#
# Nad limitem se akce NEZAHAZUJE - zařadí se se zpožděním (max. 1 akce na cíl
# za OUTGOING_THROTTLE_SPACING). Běžná dávka alertů (API + SMS, víc SMS ze
# stejného čísla) se tak doručí celá, jen rozložená v čase; případná smyčka
# se zpomalí na neškodné tempo a vyšle #SMS_LOOP.
OUTGOING_FLOOD_WINDOW_MINUTES = 5
OUTGOING_FLOOD_MAX_PER_TARGET = 5
# Totéž napříč VŠEMI pravidly - smyčka může běžet i přes víc pravidel
# (A odpoví -> pravidlo 1 pošle B -> B odpoví -> pravidlo 2 pošle A ...).
OUTGOING_FLOOD_MAX_PER_TARGET_GLOBAL = 10
OUTGOING_THROTTLE_SPACING = timedelta(minutes=1)


def _throttle_until(rule, target):
    """None = akci poslat hned (cíl je pod limitem za posledních
    OUTGOING_FLOOD_WINDOW_MINUTES minut). Jinak čas, od kdy se smí odeslat
    (next_attempt_at) - za poslední už odloženou akcí na stejný cíl."""
    now = timezone.now()
    window_start = now - timedelta(minutes=OUTGOING_FLOOD_WINDOW_MINUTES)
    if target in ('MAIL', 'TEAMS'):
        # 'MAIL'/'TEAMS' je společný zástupný cíl všech pravidel - počítat
        # jen v rámci pravidla.
        same_target = OutgoingAction.objects.filter(rule=rule, target_number=target)
        over = same_target.filter(created_at__gte=window_start).count() >= OUTGOING_FLOOD_MAX_PER_TARGET
    else:
        same_target = OutgoingAction.objects.filter(rule__isnull=False, target_number=target)
        recent = same_target.filter(created_at__gte=window_start)
        over = (
            recent.count() >= OUTGOING_FLOOD_MAX_PER_TARGET_GLOBAL
            or recent.filter(rule=rule).count() >= OUTGOING_FLOOD_MAX_PER_TARGET
        )
    if not over:
        return None

    last_delayed = (
        same_target.filter(status='PENDING', next_attempt_at__gt=now)
        .order_by('-next_attempt_at').values_list('next_attempt_at', flat=True).first()
    )
    send_at = max(last_delayed or now, now) + OUTGOING_THROTTLE_SPACING
    logger.warning(
        'Pravidlo "%s" (id=%s): cíl %s je nad limitem za %s min - akce se zpomaluje, odeslání v %s '
        '(ochrana proti zahlcení, nic se nezahazuje).',
        rule.name, rule.id, target, OUTGOING_FLOOD_WINDOW_MINUTES, timezone.localtime(send_at).strftime('%H:%M:%S'),
    )
    return send_at


def _notify_throttle_once(target):
    """#SMS_LOOP jen jednou za okno a cíl, ne při každé zpomalené akci."""
    window = timedelta(minutes=OUTGOING_FLOOD_WINDOW_MINUTES)
    already = IncomingEventLog.objects.filter(
        event_type='SYSTEM', created_at__gte=timezone.now() - window,
    ).filter(message_body__contains='#SMS_LOOP').filter(message_body__contains=f'cíl {target} ').exists()
    if already:
        return
    fire_system_health_event(
        '#SMS_LOOP',
        f'Neobvykle mnoho akcí z pravidel na cíl {target} (víc než {OUTGOING_FLOOD_MAX_PER_TARGET} '
        f'za {OUTGOING_FLOOD_WINDOW_MINUTES} min) – další se odesílají zpomaleně, max. 1 za '
        f'{int(OUTGOING_THROTTLE_SPACING.total_seconds() // 60)} min. Nic se nezahazuje; pokud jde o smyčku, '
        f'zkontroluj pravidla a číslo brány v konfiguraci.',
    )


DEFAULT_SECURITY_NOTIFICATION_RULE_NAME = 'Výchozí: Upozornění na bezpečnostní blokaci'


def get_or_create_default_security_notification_rule(user):
    """Vrátí (a při prvním použití založí) chráněné vzorové pravidlo pro
    reakci na SECURITY událost. Líně, ne jen v datové migraci - jinak by
    chybělo účtům založeným až po jejím spuštění (viz 0039_...py)."""
    rule, _ = AutomationRule.objects.get_or_create(
        owner=user,
        name=DEFAULT_SECURITY_NOTIFICATION_RULE_NAME,
        defaults={
            'description': (
                'Reaguje na automatické nebo ruční zablokování čísla '
                '(ochrana proti zahlcení SMS/API). Vypnuto, dokud si '
                'nenastavíš cílová čísla/skupiny nebo e-mail/Teams kanál.'
            ),
            'active': False,
            'priority': 10,
            'event_type': 'SECURITY',
            'match_type': 'ANY',
            'action': 'NOTIFY_NUM',
            'include_original_message': True,
            'custom_message': 'Bezpečnostní upozornění: brána zablokovala podezřelé číslo.',
            'stop_processing': True,
            'is_protected': True,
        },
    )
    return rule


def is_number_blocked(user, normalized_source):
    if not normalized_source:
        return False
    return BlockedNumber.objects.filter(owner=user, number=normalized_source).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).exists()


def _check_rate_limit_and_block(user, normalized_source, security_rule):
    """Vrátí důvod zablokování (str), pokud číslo právě překročilo limit, jinak None."""
    if not normalized_source:
        return None

    window_start = timezone.now() - timedelta(minutes=security_rule.rate_limit_window_minutes)
    recent_count = IncomingEventLog.objects.filter(
        owner=user,
        source_number=normalized_source,
        created_at__gte=window_start,
    ).count()

    if recent_count <= security_rule.rate_limit_max_events:
        return None

    reason = (
        f'Automaticky zablokováno – více než {security_rule.rate_limit_max_events} '
        f'událostí za {security_rule.rate_limit_window_minutes} min.'
    )
    BlockedNumber.objects.update_or_create(
        owner=user,
        number=normalized_source,
        defaults={
            'reason': reason,
            'expires_at': timezone.now() + timedelta(minutes=security_rule.auto_block_cooldown_minutes),
        },
    )
    return reason


def rule_log_label(rule):
    if rule.use_message_flag and rule.message_flag:
        return f'{rule.name} [příznak: {rule.message_flag}]'
    return rule.name


def event_type_matches(rule_event_type, incoming_event_type):
    normalized_rule_type = (rule_event_type or '').upper()
    normalized_incoming_type = (incoming_event_type or '').upper()

    mapping = {
        'SMS': {'SMS'},
        'API': {'API'},
        'SMS_API': {'SMS', 'API'},
        'SECURITY': {'SECURITY'},
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
        # Víc příznaků najednou (OR) - oddělené čárkou, např.
        # "#REBOOT,#LOGIN_ATTACK" - pravidlo se spustí, pokud je v textu
        # ALESPOŇ JEDEN z nich. Bez čárky (běžný případ) se chová úplně
        # stejně jako dřív - jedna přesná shoda podtextu.
        raw_flags = (rule.message_flag or '').strip().lower()
        if not raw_flags:
            return False
        required_flags = [f.strip() for f in raw_flags.split(',') if f.strip()]
        if not required_flags or not any(flag in normalized_message for flag in required_flags):
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
    normalized_source = normalize_phone_number(source_number)

    event_log = IncomingEventLog.objects.create(
        owner=user,
        event_type=event_type,
        source_number=normalized_source,
        message_body=message_body or '',
    )

    from dashboard.services import sms_dispatch

    # SMS z vlastního čísla brány nikdy nespouští pravidla - jinak by
    # jakékoliv odeslání na vlastní číslo (omylem v hromadné SMS, v cílové
    # skupině pravidla...) mohlo roztočit smyčku.
    if (event_type or '').upper() == 'SMS' and sms_dispatch.is_gateway_number(normalized_source):
        event_log.processed = True
        event_log.result_summary = (
            f'SMS z vlastního čísla brány ({normalized_source}) – pravidla se nevyhodnocují (ochrana proti smyčce).'
        )
        event_log.save(update_fields=['processed', 'result_summary'])
        return event_log, 0, 0

    security_rule = get_security_rule(user)

    # Ruční blokace platí vždy - je to explicitní rozhodnutí administrátora,
    # nezávislé na přepínači automatické ochrany.
    if is_number_blocked(user, normalized_source):
        event_log.processed = True
        event_log.result_summary = f'Číslo {normalized_source} je blokované – událost ignorována, pravidla se nevyhodnocují.'
        event_log.save(update_fields=['processed', 'result_summary'])
        return event_log, 0, 0

    # Automatická ochrana proti zahlcení jde vypnout přes SecurityRule.active
    # (Django Admin) - ruční blokace výše tím není dotčená.
    if security_rule.active:
        block_reason = _check_rate_limit_and_block(user, normalized_source, security_rule)
        if block_reason:
            event_log.processed = True
            event_log.result_summary = f'{block_reason} Tato a další události z tohoto čísla se dočasně ignorují.'
            event_log.save(update_fields=['processed', 'result_summary'])

            # Samostatná bezpečnostní událost, na kterou mohou reagovat
            # pravidla s event_type='SECURITY' (např. upozornit administrátora).
            # Jde o nový IncomingEventLog, ne pokračování téhle - jinak by ho
            # o pár řádků výš znovu chytil is_number_blocked() a nic by se
            # nevyhodnotilo.
            _fire_security_event(user, normalized_source, block_reason)
            return event_log, 0, 0

    # Opakované SMS ze stejného čísla se vyhodnotí vždy - smyčku řeší číslo
    # brány (výše a ve workeru) a zpomalení v _throttle_until, ne zahazování.
    return _evaluate_rules(user, event_log, event_type, source_number, message_body, source_device_object)


def _fire_security_event(user, source_number, reason):
    security_log = IncomingEventLog.objects.create(
        owner=user,
        event_type='SECURITY',
        source_number=source_number,
        message_body=reason,
    )
    return _evaluate_rules(user, security_log, 'SECURITY', source_number, reason)


def fire_system_health_event(flag, message, source_number=''):
    """Stavová/bezpečnostní událost celé brány (restart RPi, pokus o útok na
    přihlášení, přihlášení admina...) - na rozdíl od běžných událostí není
    vázaná na data jednoho uživatele, proto se vytvoří samostatně pro
    KAŽDÉHO admina/superusera (access.is_admin) - každý si pak reaguje
    vlastním pravidlem (event_type=SYSTEM, příznak `flag`). Stejný vzor jako
    _fire_security_event výše, jen pro víc vlastníků najednou."""
    from dashboard.access import is_admin

    full_message = f'{message} {flag}'.strip()
    admins = [u for u in User.objects.filter(is_active=True) if is_admin(u)]
    for admin in admins:
        event_log = IncomingEventLog.objects.create(
            owner=admin,
            event_type='SYSTEM',
            source_number=source_number,
            message_body=full_message,
        )
        _evaluate_rules(admin, event_log, 'SYSTEM', source_number, full_message)


def _queue_first_contact_notice(rule, user, event_log, target):
    """Pokud má pravidlo zapnuté notify_first_contact a tohle je první kontakt
    daného čísla tímto pravidlem (podle historie OutgoingAction), zařadí navíc
    jednorázovou informační SMS. Musí se zavolat PŘED vytvořením hlavní
    NOTIFY_SMS/FORWARD_INFO akce pro tenhle cíl - jinak by check `.exists()`
    už viděl tu právě vytvořenou akci a first-contact by se nikdy nespustil."""
    if not rule.notify_first_contact:
        logger.info('Pravidlo "%s" (id=%s): notify_first_contact je vypnuté, info SMS se přeskakuje.', rule.name, rule.id)
        return False

    already_contacted = OutgoingAction.objects.filter(rule=rule, target_number=target).exists()
    if already_contacted:
        logger.info(
            'Pravidlo "%s" (id=%s): číslo %s už bylo tímto pravidlem dřív kontaktováno, info SMS se nezařazuje.',
            rule.name, rule.id, target,
        )
        return False

    message = rule.first_contact_message.strip() if rule.first_contact_message else ''
    if not message:
        message = f'Byl jsi zařazen do automatizace „{rule.name}“.'

    OutgoingAction.objects.create(
        owner=user,
        event_log=event_log,
        rule=rule,
        action_type='INFO_SMS',
        target_number=target,
        payload_message=message,
        status='PENDING',
    )
    logger.info('Pravidlo "%s" (id=%s): zařazena info SMS pro první kontakt čísla %s.', rule.name, rule.id, target)
    return True


def resolve_rule_targets(rule):
    """Vrátí normalizovaná cílová čísla pravidla podle jeho akce - stejná
    logika jako uvnitř _evaluate_rules, sdílená i s fire_first_contact_on_save
    (odeslání informační SMS hned po uložení pravidla, ne až při události)."""
    targets = []

    if rule.action == 'NOTIFY_NUM':
        for phone in rule.target_numbers.filter(active=True):
            normalized = normalize_phone_number(phone.number)
            if normalized:
                targets.append(normalized)
    elif rule.action == 'NOTIFY_GRP':
        for group in rule.target_groups.all():
            for phone in group.phone_numbers.filter(active=True):
                normalized = normalize_phone_number(phone.number)
                if normalized:
                    targets.append(normalized)
    elif rule.action == 'FORWARD':
        for phone in rule.target_numbers.filter(active=True):
            normalized = normalize_phone_number(phone.number)
            if normalized:
                targets.append(normalized)
        if not targets:
            legacy_target = normalize_phone_number(rule.forward_to_number)
            if legacy_target:
                targets = [legacy_target]

    return sorted(set(targets))


def fire_first_contact_on_save(rule):
    """Pro pravidla s first_contact_timing='ON_SAVE' - zavolat z
    views.rule_create/rule_update hned po uložení pravidla. Používá stejný
    dedup (OutgoingAction historie) jako běžné posílání za běhu, takže
    opakované uložení pravidla znovu neobtěžuje už kontaktovaná čísla,
    jen nově přidaná."""
    if not rule.notify_first_contact or rule.first_contact_timing != 'ON_SAVE':
        return 0

    targets = resolve_rule_targets(rule)
    if not targets:
        logger.info('Pravidlo "%s" (id=%s): ON_SAVE info SMS - žádná cílová čísla, nic se nezařazuje.', rule.name, rule.id)
        return 0

    event_log = IncomingEventLog.objects.create(
        owner=rule.owner,
        event_type='SYSTEM',
        source_number='',
        message_body=f'Vytvořeno/upraveno pravidlo „{rule.name}“ - informační SMS se posílá hned po uložení.',
        processed=True,
        result_summary=f'Automaticky vygenerováno při uložení pravidla „{rule.name}“ (first_contact_timing=ON_SAVE).',
    )

    queued = 0
    for target in targets:
        if _queue_first_contact_notice(rule, rule.owner, event_log, target):
            queued += 1

    return queued


def _build_notification_payload(rule, default_text, source_number, message_body):
    """Sestaví text zprávy pro NOTIFY_NUM/NOTIFY_GRP/FORWARD. include_source_number
    se aplikuje nezávisle na tom, jestli je nastavený vlastní text (dřív se
    zdrojové číslo objevovalo jen v automaticky generovaném textu bez
    custom_message - viz migrace 0049)."""
    payload = rule.custom_message.strip() if rule.custom_message else ''
    if not payload:
        payload = default_text

    if rule.include_source_number:
        normalized_source = normalize_phone_number(source_number)
        if normalized_source:
            payload = f'{payload} (od čísla {normalized_source})'

    if rule.include_original_message and message_body:
        payload = f'{payload}\nObsah: {message_body}'

    return payload


def _evaluate_rules(user, event_log, event_type, source_number, message_body, source_device_object=None):
    summaries = []
    matched_count = 0
    queued_count = 0
    throttled = {}  # cíl -> nejpozdější čas odeslání

    def queue_action(rule, action_type, target, payload):
        """Zařadí akci vždy - nad limitem jen se zpožděním (_throttle_until)."""
        send_at = _throttle_until(rule, target)
        OutgoingAction.objects.create(
            owner=user,
            event_log=event_log,
            rule=rule,
            action_type=action_type,
            target_number=target,
            payload_message=payload,
            status='PENDING',
            next_attempt_at=send_at,
        )
        if send_at:
            throttled[target] = max(send_at, throttled.get(target, send_at))

    rules = AutomationRule.objects.filter(active=True).filter(
        Q(owner=user) | Q(users=user)
    ).distinct().order_by('priority', 'id')

    for rule in rules:
        if not rule_matches_event(rule, event_type, source_number, message_body, source_device_object=source_device_object):
            continue


        matched_count += 1
        log_rule_name = rule_log_label(rule)
        logger.info(
            'Pravidlo "%s" (id=%s) se shoduje: action=%s, notify_first_contact=%s.',
            rule.name, rule.id, rule.action, rule.notify_first_contact,
        )

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

            payload = _build_notification_payload(rule, f'[{event_type}] událost', source_number, message_body)

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

            # Nezávislé na notify_via_sms - první kontakt je vlastní
            # zaškrtávátko, ne podřízené kanálu SMS. Admin může chtít hlavní
            # notifikaci jen e-mailem/Teams a přesto poslat jednorázovou
            # info SMS novému číslu. Vypnuté/přeskočené případy řeší a loguje
            # _queue_first_contact_notice sama. Jen ON_TRIGGER - ON_SAVE se
            # odbaví jednorázově ve views.rule_create/rule_update, ne tady.
            if rule.first_contact_timing == 'ON_TRIGGER':
                for target in targets:
                    if _queue_first_contact_notice(rule, user, event_log, target):
                        queued_count += 1
                        rule_queued_count += 1

            if rule.notify_via_sms:
                if not targets:
                    summaries.append(f'Pravidlo "{log_rule_name}": kanál SMS přeskočen, protože chybí cílová čísla/skupiny.')
                else:
                    for target in targets:
                        queue_action(rule, 'NOTIFY_SMS', target, payload)
                        queued_count += 1
                        rule_queued_count += 1

            if rule.notify_via_email:
                queue_action(rule, 'NOTIFY_EMAIL', 'MAIL', payload)
                queued_count += 1
                rule_queued_count += 1

            if rule.notify_via_teams:
                queue_action(rule, 'NOTIFY_TEAMS', 'TEAMS', payload)
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
                payload = _build_notification_payload(rule, f'[{event_type}] předání na číslo', source_number, message_body)

                for target in targets:
                    if rule.first_contact_timing == 'ON_TRIGGER' and _queue_first_contact_notice(rule, user, event_log, target):
                        queued_count += 1
                    queue_action(rule, 'FORWARD_INFO', target, payload)
                    queued_count += 1

                summaries.append(
                    f'Pravidlo "{log_rule_name}": akce „Předat na číslo“ zařazena do fronty pro {len(targets)} cílových čísel.'
                )

        if rule.stop_processing:
            summaries.append('Zpracování ukončeno podle priority pravidel.')
            break

    if throttled:
        details = ', '.join(
            f'{target} (nejpozději {timezone.localtime(send_at):%H:%M})' for target, send_at in sorted(throttled.items())
        )
        summaries.append(
            f'Zpomaleno (ochrana proti zahlcení, nic se nezahazuje): {details} – na cíl šlo za posledních '
            f'{OUTGOING_FLOOD_WINDOW_MINUTES} min víc než {OUTGOING_FLOOD_MAX_PER_TARGET} akcí.'
        )
        if event_type != 'SYSTEM':
            # SYSTEM události samy nevyvolávají další #SMS_LOOP (jinak by
            # upozornění na zahlcení mohlo zahlcení samo prodlužovat).
            for target in throttled:
                _notify_throttle_once(target)

    if matched_count == 0:
        summaries.append('Nebyla nalezena žádná aktivní pravidla pro tuto událost.')

    event_log.processed = True
    event_log.result_summary = '\n'.join(summaries)
    event_log.save(update_fields=['processed', 'result_summary'])

    return event_log, matched_count, queued_count

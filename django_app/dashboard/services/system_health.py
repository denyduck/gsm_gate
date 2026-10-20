import logging
from datetime import timedelta

from django.utils import timezone

from dashboard.models import OutgoingAction, SystemState
from dashboard.services import selftest
from dashboard.services.rules_engine import fire_system_health_event

logger = logging.getLogger(__name__)

# Drobné odchylky při opakovaném čtení /proc/uptime (desetiny/jednotky
# sekund) by jinak vypadaly jako nový boot - reálný restart se liší o
# minuty/desítky sekund přinejmenším, tahle tolerance je bezpečně pod tím.
REBOOT_DETECTION_TOLERANCE_SECONDS = 30

# Jediný zdroj popisků příznaků pro SYSTEM události - použito v rule_detail
# view (dashboard/views.py) i v rule_form.html, ať se to nerozchází.
SYSTEM_FLAG_DESCRIPTIONS = [
    ('#REBOOT', 'RPi bylo restartováno (ne jen restart kontejneru).'),
    ('#LOGIN_ADMIN', 'přihlásil se admin/superuser.'),
    ('#LOGIN_ATTACK', 'překročen limit neúspěšných pokusů o přihlášení (10 za 5 min).'),
    ('#DISK_LOW', 'málo místa na disku (nebo se uvolnilo).'),
    ('#BACKUP_OLD', 'poslední záloha je starší než 7 dní (nebo chybí/je zase čerstvá).'),
    ('#CONFIG_WARN', 'problém s bezpečnostní konfigurací (DEBUG/SECRET_KEY/ALLOWED_HOSTS).'),
    ('#QUEUE_PROBLEM', 'fronta odchozích akcí je zaseknutá / hodně chyb (nebo se vyčistila).'),
]


def _read_host_boot_time():
    """Čas bootu HOSTITELE (RPi), ne kontejneru - /proc/uptime odráží reálný
    uptime jádra. Tohle číslo je sdílené mezi hostem a kontejnerem bez
    ohledu na PID namespace (jádro ho nenamespacuje), takže funguje i bez
    zvláštního přístupu/mountu v docker-compose.yml."""
    with open('/proc/uptime') as f:
        uptime_seconds = float(f.read().split()[0])
    return timezone.now() - timedelta(seconds=uptime_seconds)


def check_reboot():
    """Zavolat jednou za cyklus gsm_worker (viz gsm_worker.py) - mimo
    try/except na modem, ať detekce restartu funguje i chvíli po výpadku,
    než se modem znovu zaregistruje v síti."""
    try:
        boot_time = _read_host_boot_time()
    except OSError as e:
        logger.warning('Nepodařilo se přečíst /proc/uptime pro detekci restartu RPi: %s', e)
        return

    state = SystemState.load()

    if state.last_known_boot_time is None:
        # První běh po nasazení appky - jen si zapamatovat výchozí stav,
        # ať se restart "detekuje" i při naprosto prvním startu appky.
        state.last_known_boot_time = boot_time
        state.save(update_fields=['last_known_boot_time'])
        return

    delta_seconds = abs((boot_time - state.last_known_boot_time).total_seconds())
    if delta_seconds > REBOOT_DETECTION_TOLERANCE_SECONDS:
        fire_system_health_event(
            '#REBOOT',
            f'Raspberry Pi bylo restartováno (nový čas bootu: {timezone.localtime(boot_time):%d.%m.%Y %H:%M:%S}).',
        )
        state.last_known_boot_time = boot_time
        state.save(update_fields=['last_known_boot_time'])


# Stavový rank pro rozpoznání ZHORŠENÍ vs. OBNOVENÍ (stejná stupnice jako
# services/selftest.py).
_STATUS_RANK = {'OK': 0, 'WARN': 1, 'ERROR': 2}


def _check_outgoing_queue_global():
    """Stejná logika jako selftest.check_outgoing_queue(), jen přes
    VŠECHNY uživatele najednou (ne per-owner) - tahle kontrola běží z
    workeru, který obsluhuje frontu pro celou bránu, ne jednoho uživatele."""
    stuck_pending = OutgoingAction.objects.filter(
        status='PENDING', created_at__lt=timezone.now() - timedelta(minutes=10),
    ).count()
    failed_recent = OutgoingAction.objects.filter(
        status='FAILED', created_at__gte=timezone.now() - timedelta(hours=24),
    ).count()

    if stuck_pending:
        return 'ERROR', f'{stuck_pending} odchozích akcí čeká na zpracování déle než 10 min (přes všechny účty).'
    if failed_recent:
        return 'WARN', f'{failed_recent} odchozích akcí za posledních 24 h selhalo (přes všechny účty).'
    return 'OK', 'Fronta odchozích akcí je v pořádku.'


# (klíč pro uložený stav v SystemState.check_states, funkce vracející buď
# selftest "result" dict ({'status', 'message', ...}), nebo (status,
# message) tuple, výsledný příznak pro pravidla).
_WATCHED_CHECKS = [
    ('disk_space', selftest.check_disk_space, '#DISK_LOW'),
    ('last_backup', selftest.check_last_backup, '#BACKUP_OLD'),
    ('debug_mode', selftest.check_debug_mode, '#CONFIG_WARN'),
    ('secret_key', selftest.check_secret_key, '#CONFIG_WARN'),
    ('allowed_hosts', selftest.check_allowed_hosts, '#CONFIG_WARN'),
    ('outgoing_queue', _check_outgoing_queue_global, '#QUEUE_PROBLEM'),
]


def check_periodic_health():
    """Zavolat jednou za cyklus gsm_worker - porovná vybrané kontroly
    (stejná logika/prahy jako Sebediagnostika, dashboard/services/selftest.py,
    žádná duplicita pravidel) s posledním zaznamenaným stavem a vyšle
    SYSTEM událost jen při ZMĚNĚ (zhoršení nebo návrat na OK po horším
    stavu) - ne při každém cyklu, kdy problém jen přetrvává."""
    state = SystemState.load()
    known_states = dict(state.check_states or {})
    changed = False

    for key, check_fn, flag in _WATCHED_CHECKS:
        try:
            result = check_fn()
        except Exception:
            logger.exception('Chyba při periodické kontrole zdraví brány (%s)', key)
            continue

        if isinstance(result, dict):
            status, message = result['status'], result['message']
        else:
            status, message = result

        previous = known_states.get(key)
        if previous == status:
            continue

        changed = True
        known_states[key] = status

        if previous is None:
            # První běh po nasazení appky - jen zapamatovat výchozí stav,
            # ať neexistující "historie" nevygeneruje falešné zhoršení.
            continue

        if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(previous, 0):
            fire_system_health_event(flag, f'Zhoršení ({key}): {message}')
        elif status == 'OK':
            fire_system_health_event(flag, f'Obnoveno ({key}): {message}')

    if changed:
        state.check_states = known_states
        state.save(update_fields=['check_states'])

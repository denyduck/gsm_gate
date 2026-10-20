import logging
from datetime import timedelta

from django.utils import timezone

from dashboard.models import SystemState
from dashboard.services.rules_engine import fire_system_health_event

logger = logging.getLogger(__name__)

# Drobné odchylky při opakovaném čtení /proc/uptime (desetiny/jednotky
# sekund) by jinak vypadaly jako nový boot - reálný restart se liší o
# minuty/desítky sekund přinejmenším, tahle tolerance je bezpečně pod tím.
REBOOT_DETECTION_TOLERANCE_SECONDS = 30


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

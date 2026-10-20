import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from dashboard.access import is_admin
from dashboard.services.rules_engine import fire_system_health_event

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def notify_admin_login(sender, request, user, **kwargs):
    """Upozornění na přihlášení admina/superusera (access.is_admin) - viz
    fire_system_health_event, reaguje se přes běžné pravidlo
    (event_type=SYSTEM, příznak #LOGIN_ADMIN). Běžné přihlášení uživatele
    bez téhle role nic nespouští."""
    if not is_admin(user):
        return

    client_ip = request.META.get('REMOTE_ADDR', 'neznámá IP') if request else 'neznámá IP'
    try:
        fire_system_health_event(
            '#LOGIN_ADMIN',
            f'Přihlášení administrátora „{user.username}“ (IP: {client_ip}).',
            source_number=client_ip,
        )
    except Exception:
        logger.exception('Chyba při generování události přihlášení admina')

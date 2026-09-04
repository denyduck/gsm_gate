import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from dashboard.models import GatewaySettings, OutgoingAction, SecurityRule

STATUS_RANK = {'OK': 0, 'WARN': 1, 'ERROR': 2}


def _result(name, status, message, recommendation=''):
    return {'name': name, 'status': status, 'message': message, 'recommendation': recommendation}


def check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return _result('Databáze', 'OK', 'Připojení k PostgreSQL funguje.')
    except Exception as exc:
        return _result(
            'Databáze', 'ERROR', f'Nepodařilo se připojit: {exc}',
            'Zkontroluj kontejner db (docker compose ps, docker compose logs db).',
        )


def check_debug_mode():
    if settings.DEBUG:
        return _result(
            'DEBUG režim', 'WARN', 'DEBUG je zapnutý.',
            'Nastav DJANGO_DEBUG=False v .env pro produkci - DEBUG odhaluje tracebacky, cesty a SQL komukoliv.',
        )
    return _result('DEBUG režim', 'OK', 'DEBUG je vypnutý.')


def check_secret_key():
    if settings.SECRET_KEY.startswith('django-insecure-'):
        return _result(
            'SECRET_KEY', 'ERROR', 'Používá se nebezpečný výchozí klíč.',
            'Vygeneruj vlastní DJANGO_SECRET_KEY a vlož do .env (viz docs/nasazeni-a-obnova.md).',
        )
    return _result('SECRET_KEY', 'OK', 'Vlastní klíč je nastavený.')


def check_allowed_hosts():
    if '*' in settings.ALLOWED_HOSTS:
        return _result(
            'ALLOWED_HOSTS', 'WARN', 'Obsahuje wildcard "*" - appka přijme požadavek na jakýkoliv hostname.',
            'Zúžit na skutečnou IP/hostname brány v .env.',
        )
    return _result('ALLOWED_HOSTS', 'OK', ', '.join(settings.ALLOWED_HOSTS))


def check_static_files():
    manifest_path = Path(settings.STATIC_ROOT) / 'staticfiles.json'
    if not manifest_path.exists():
        return _result(
            'Static soubory', 'ERROR', 'Chybí WhiteNoise manifest (staticfiles.json).',
            'Spusť `docker compose exec web python manage.py collectstatic --noinput --clear` nebo restartuj kontejner web.',
        )
    return _result('Static soubory', 'OK', 'Manifest static souborů existuje.')


def check_disk_space():
    usage = shutil.disk_usage(settings.BASE_DIR)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 300:
        return _result(
            'Volné místo na disku', 'ERROR', f'Jen {free_mb:.0f} MB volno.',
            'Ulehči disku - smaž staré zálohy/logy (Reset dat), případně rozšiř úložiště.',
        )
    if free_mb < 1000:
        return _result('Volné místo na disku', 'WARN', f'{free_mb:.0f} MB volno.', 'Sleduj místo na disku, brzy může dojít.')
    return _result('Volné místo na disku', 'OK', f'{free_mb:.0f} MB volno.')


def check_last_backup():
    backup_dir = Path(settings.BASE_DIR) / 'backups'
    files = sorted(backup_dir.glob('gsm_gate_*_backup_*.json'), key=lambda p: p.stat().st_mtime, reverse=True) if backup_dir.exists() else []

    if not files:
        return _result(
            'Poslední záloha', 'WARN', 'V backups/ nebyl nalezen žádný export.',
            'Stáhni zálohu ručně (Zálohování v menu) nebo nastav scripts/gsm-backup.timer.',
        )

    age_days = (timezone.now().timestamp() - files[0].stat().st_mtime) / 86400
    if age_days > 7:
        return _result(
            'Poslední záloha', 'WARN', f'Poslední záloha je stará {age_days:.1f} dne.',
            'Zvaž pravidelné zálohování (scripts/gsm-backup.timer) nebo ji stáhni ručně.',
        )
    return _result('Poslední záloha', 'OK', f'Poslední záloha stará {age_days:.1f} dne ({files[0].name}).')


def check_gateway_settings(user):
    gateway = GatewaySettings.objects.filter(user=user).first()
    if gateway is None:
        return _result(
            'Nastavení brány', 'WARN', 'Pro tento účet ještě neexistuje nastavení brány.',
            'Otevři Konfigurace a ulož nastavení alespoň jednou.',
        )
    return _result('Nastavení brány', 'OK', 'Nastavení existuje.')


def check_worker_heartbeat(user):
    gateway = GatewaySettings.objects.filter(user=user).first()
    if gateway is None or gateway.last_signal_checked_at is None:
        return _result(
            'Worker / signál modemu', 'WARN', 'Zatím nebyla zaznamenána žádná kontrola signálu.',
            'Zkontroluj, jestli běží gsm_worker (`docker compose --profile rpi ps`) a jestli je GSM_ENABLED=true.',
        )

    threshold_seconds = max(settings.GSM_WORKER_INTERVAL * 6, 300)
    age_seconds = (timezone.now() - gateway.last_signal_checked_at).total_seconds()

    if age_seconds > threshold_seconds:
        return _result(
            'Worker / signál modemu', 'ERROR', f'Poslední kontrola signálu byla před {int(age_seconds // 60)} min.',
            'Worker pravděpodobně neběží nebo se nedaří připojit k modemu - viz docs/modem-diagnostika.md.',
        )
    return _result('Worker / signál modemu', 'OK', f'Naposledy před {int(age_seconds)} s (limit {threshold_seconds} s).')


def check_security_rule(user):
    rule = SecurityRule.objects.filter(owner=user).first()
    if rule is None:
        return _result('Bezpečnostní pravidlo', 'WARN', 'Zatím nebylo založeno (založí se automaticky při první příchozí události).')
    if not rule.active:
        return _result(
            'Bezpečnostní pravidlo', 'WARN', 'Ochrana proti zahlcení SMS/API je vypnutá.',
            'Zvaž zapnutí v Django Adminu (SecurityRule), pokud brána přijímá zprávy z nedůvěryhodných zdrojů.',
        )
    return _result('Bezpečnostní pravidlo', 'OK', f'Aktivní - limit {rule.rate_limit_max_events} událostí / {rule.rate_limit_window_minutes} min.')


def check_outgoing_queue(user):
    failed_recent = OutgoingAction.objects.filter(
        owner=user, status='FAILED', created_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    stuck_pending = OutgoingAction.objects.filter(
        owner=user, status='PENDING', created_at__lt=timezone.now() - timedelta(minutes=10),
    ).count()

    if stuck_pending:
        return _result(
            'Fronta odchozích akcí', 'ERROR', f'{stuck_pending} akcí čeká na zpracování déle než 10 min.',
            'Worker pravděpodobně neběží nebo je zaseknutý - zkontroluj `docker compose --profile rpi logs gsm_worker`.',
        )
    if failed_recent:
        return _result(
            'Fronta odchozích akcí', 'WARN', f'{failed_recent} akcí za posledních 24 h selhalo.',
            'Zkontroluj detail akcí v Odchozích akcích (execution_detail) a stav modemu.',
        )
    return _result('Fronta odchozích akcí', 'OK', 'Žádné zaseknuté ani nedávno selhané akce.')


GLOBAL_CHECKS = [
    check_database,
    check_debug_mode,
    check_secret_key,
    check_allowed_hosts,
    check_static_files,
    check_disk_space,
    check_last_backup,
]

USER_CHECKS = [
    check_gateway_settings,
    check_worker_heartbeat,
    check_security_rule,
    check_outgoing_queue,
]


def run_self_test(user):
    results = [check() for check in GLOBAL_CHECKS]
    results += [check(user) for check in USER_CHECKS]

    overall = 'OK'
    for result in results:
        if STATUS_RANK[result['status']] > STATUS_RANK[overall]:
            overall = result['status']

    return overall, results

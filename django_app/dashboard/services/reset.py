# Hromadné mazání dat brány (stránka "Zálohování", jen pro superusera).
# Chráněná systémová pravidla (AutomationRule.is_protected) a SecurityRule
# se nikdy nemažou - jen se SecurityRule resetuje na výchozí limity, stejně
# jako u jednotlivého mazání jinde v appce (rules_engine/views).

from dashboard.models import (
    AutomationRule,
    BlockedNumber,
    DeviceObject,
    GatewaySettings,
    Group,
    IncomingEventLog,
    PhoneNumber,
    SecurityRule,
    SignalReading,
)

CONFIRM_PHRASE = 'SMAZAT'


def reset_numbers(user):
    count, _ = PhoneNumber.objects.filter(owner=user).delete()
    return count


def reset_groups(user):
    count, _ = Group.objects.filter(owner=user).delete()
    return count


def reset_objects(user):
    count, _ = DeviceObject.objects.filter(owner=user).delete()
    return count


def reset_rules(user):
    count, _ = AutomationRule.objects.filter(owner=user, is_protected=False).delete()
    return count


def reset_blocked_numbers(user):
    count, _ = BlockedNumber.objects.filter(owner=user).delete()
    return count


def reset_logs(user):
    # OutgoingAction.event_log je on_delete=CASCADE, takže smazáním
    # IncomingEventLog zmizí i navázané odchozí akce.
    count, _ = IncomingEventLog.objects.filter(owner=user).delete()
    return count


def reset_signal_history(user):
    count, _ = SignalReading.objects.filter(owner=user).delete()
    return count


def reset_gateway_settings(user):
    GatewaySettings.objects.filter(user=user).update(
        pin_code='',
        delivery_reports=True,
        allow_incoming_sms=True,
        webhook_url='',
        last_signal_quality=None,
        last_signal_checked_at=None,
    )


def reset_security_rule(user):
    SecurityRule.objects.filter(owner=user).update(
        active=True,
        rate_limit_window_minutes=10,
        rate_limit_max_events=20,
        auto_block_cooldown_minutes=30,
    )


RESET_ACTIONS = {
    'numbers': ('Telefonní čísla', reset_numbers),
    'groups': ('Skupiny', reset_groups),
    'objects': ('Objekty zařízení', reset_objects),
    'rules': ('Automatizační pravidla', reset_rules),
    'blocked': ('Blokovaná čísla', reset_blocked_numbers),
    'logs': ('Historie událostí a odchozích akcí', reset_logs),
    'signal_history': ('Historie síly signálu', reset_signal_history),
}


def reset_all(user):
    summary = {label: func(user) for label, func in RESET_ACTIONS.values()}
    reset_gateway_settings(user)
    reset_security_rule(user)
    return summary

import io

from django.core import management

# Sdílené definice pro export/import dat (views.backup_* i management příkaz
# export_backup) - Django dumpdata/loaddata místo vlastní serializace.

DATA_MODELS = [
    'dashboard.Group',
    'dashboard.PhoneNumber',
    'dashboard.UserGroupVisibilityOverride',
    'dashboard.DeviceObject',
    'dashboard.DeviceObjectApiCredential',
    'dashboard.GatewaySettings',
    'dashboard.AutomationRule',
    'dashboard.SecurityRule',
    'dashboard.BlockedNumber',
    'dashboard.IncomingEventLog',
    'dashboard.OutgoingAction',
    'auth.User',
]

SETTINGS_MODELS = [
    'dashboard.GatewaySettings',
    'dashboard.SecurityRule',
    'auth.User',
]

MODEL_SETS = {
    'data': DATA_MODELS,
    'settings': SETTINGS_MODELS,
}


def dump_models(model_labels):
    buffer = io.StringIO()
    management.call_command(
        'dumpdata', *model_labels,
        format='json', indent=2,
        use_natural_foreign_keys=True, use_natural_primary_keys=True,
        stdout=buffer,
    )
    return buffer.getvalue()

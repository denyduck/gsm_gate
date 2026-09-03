from django.contrib import admin

from .models import SecurityRule

# Pozor: AutomationRule je už zaregistrovaný v gsm_gate/admin.py (viz
# AutomationRuleAdmin tam) - ochrana is_protected proti smazání je doplněná
# přímo do jeho has_delete_permission, ne tady (duplicitní @admin.register
# by způsobil AlreadyRegistered).


@admin.register(SecurityRule)
class SecurityRuleAdmin(admin.ModelAdmin):
    """Bezpečnostní pravidlo proti zahlcení SMS/API událostmi.

    Singleton na uživatele (vzniká automaticky přes get_or_create v
    rules_engine.py) — jde jen zapnout/vypnout a upravit prahy, ne přidat
    ručně další řádek ani smazat existující.
    """

    list_display = (
        'owner',
        'active',
        'rate_limit_window_minutes',
        'rate_limit_max_events',
        'auto_block_cooldown_minutes',
        'updated_at',
    )
    list_editable = ('active',)
    list_filter = ('active',)
    fields = (
        'owner',
        'active',
        'rate_limit_window_minutes',
        'rate_limit_max_events',
        'auto_block_cooldown_minutes',
        'updated_at',
    )
    readonly_fields = ('owner', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

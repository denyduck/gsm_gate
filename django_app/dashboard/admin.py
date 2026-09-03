from django.contrib import admin

from .models import AutomationRule, SecurityRule


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    """Automatizační pravidla - běžná pravidla jdou mazat/upravovat normálně,
    ale pravidla s `is_protected=True` (např. výchozí bezpečnostní upozornění)
    nejde smazat ani odsud - jen zapnout/vypnout a nastavit cíle/kanály.
    """

    list_display = ('name', 'owner', 'event_type', 'action', 'active', 'is_protected', 'priority')
    list_editable = ('active',)
    list_filter = ('is_protected', 'active', 'event_type', 'action')
    search_fields = ('name', 'description', 'owner__username')
    filter_horizontal = ('users', 'source_groups', 'source_objects', 'target_numbers', 'target_groups')

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_protected:
            return False
        return super().has_delete_permission(request, obj)


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

# Admin rozhraní pro modely Group a PhoneNumber
# slouží k pohodlné správě přes Django admin a zobrazení důležitých polí

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django import forms
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from dashboard.models import (
    DeviceObject,
    Group,
    PhoneNumber,
    GatewaySettings,
    AutomationRule,
    IncomingEventLog,
    OutgoingAction,
    UserGroupVisibilityOverride,
)

admin.site.site_header = 'Správa GSM brány'
admin.site.site_title = 'Admin GSM brány'
admin.site.index_title = 'Administrace systému'


def approve_users(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    modeladmin.message_user(request, f'Schváleno uživatelů: {count}')


approve_users.short_description = 'Schválit vybrané uživatele (aktivovat účet)'


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(DjangoUserAdmin):
    list_filter = DjangoUserAdmin.list_filter + ('is_active',)
    actions = (approve_users,)


class GroupAssignmentFilter(admin.SimpleListFilter):
    title = 'Přiřazení do skupiny'
    parameter_name = 'group_assignment'

    def lookups(self, request, model_admin):
        return (
            ('with_group', 'Se skupinou'),
            ('without_group', 'Bez skupiny'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'with_group':
            return queryset.filter(groups__isnull=False).distinct()
        if value == 'without_group':
            return queryset.filter(groups__isnull=True).distinct()
        return queryset

# Funkce pro zobrazení všech uživatelů M2M v jednom sloupci
def users_list(obj):
    return ", ".join([u.username for u in obj.users.all()])
users_list.short_description = "Uživatelé"


##################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Phone Numbers"
##################################################################################################
# Registrace modelu PhoneNumber do admin rozhraní django a další přdané funkce
@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('number', 'description', 'active', 'owner', users_list)
    list_filter = ('active', 'owner', 'groups', GroupAssignmentFilter)
    search_fields = ('number', 'description', 'owner__username')
    filter_horizontal = ('groups', 'users')  # funguje jen pokud pole groups a users existuje
    raw_id_fields = ('owner',)  # místo neexistujícího 'user'
    ordering = ('number',)
    fieldsets = (
        (None, {
            'fields': ('number', 'description', 'active', 'owner', 'groups', 'users')
        }),
    )

####################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Groups"
####################################################################################################
# Registrace modelu Group do admin rozhraní django
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'id', 'owner', users_list)
    search_fields = ('name', 'description')
    filter_horizontal = ('users',)
    autocomplete_fields = ('owner',)


class UserGroupVisibilityOverrideAdminForm(forms.ModelForm):
    class Meta:
        model = UserGroupVisibilityOverride
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        selected_group = None
        if self.instance and self.instance.pk:
            selected_group = self.instance.group
        elif self.data.get('group'):
            selected_group = Group.objects.filter(pk=self.data.get('group')).first()

        if selected_group is not None:
            self.fields['hidden_numbers'].queryset = selected_group.phone_numbers.order_by('number')
        else:
            self.fields['hidden_numbers'].queryset = PhoneNumber.objects.none()


@admin.register(UserGroupVisibilityOverride)
class UserGroupVisibilityOverrideAdmin(admin.ModelAdmin):
    form = UserGroupVisibilityOverrideAdminForm
    list_display = ('user', 'group', 'hidden_numbers_count')
    search_fields = ('user__username', 'group__name', 'hidden_numbers__number')
    autocomplete_fields = ('user', 'group')
    filter_horizontal = ('hidden_numbers',)

    def hidden_numbers_count(self, obj):
        return obj.hidden_numbers.count()
    hidden_numbers_count.short_description = 'Skrytých čísel'


@admin.register(GatewaySettings)
class GatewaySettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'serial_port', 'network_mode', 'auto_start_gateway', 'updated_at')
    list_filter = ('network_mode', 'auto_start_gateway', 'allow_incoming_sms', 'delivery_reports')
    search_fields = ('user__username', 'serial_port', 'apn')


class AutomationRuleAdminForm(forms.ModelForm):
    PRESET_CHOICES = [
        ('', '— Bez předvolby —'),
        ('OBJECT_FLAG', 'Objekt + příznak'),
        ('OBJECT_SIMPLE', 'Pouze objekt'),
        ('EXACT_FLAG', 'Číslo + příznak'),
    ]

    quick_preset = forms.ChoiceField(
        label='Rychlá předvolba',
        choices=PRESET_CHOICES,
        required=False,
        help_text='Volitelně nastaví kombinaci polí pro nejčastější scénáře.',
    )

    assign_to_users = forms.ModelMultipleChoiceField(
        label='Použít také pro vybrané uživatele',
        queryset=User.objects.all().order_by('username'),
        required=False,
        help_text='Vybraní uživatelé pravidlo uvidí a použijí při vyhodnocení, ale nebudou jeho vlastníky.',
        widget=admin.widgets.FilteredSelectMultiple('Uživatelé', is_stacked=False),
    )

    class Meta:
        model = AutomationRule
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['assign_to_users'].initial = self.instance.users.all()

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get('quick_preset')
        if not preset:
            return cleaned

        if preset == 'OBJECT_FLAG':
            cleaned['match_type'] = 'OBJECT'
            cleaned['use_message_flag'] = True
            if not (cleaned.get('message_flag') or '').strip():
                cleaned['message_flag'] = '#OBJ'
        elif preset == 'OBJECT_SIMPLE':
            cleaned['match_type'] = 'OBJECT'
            cleaned['use_message_flag'] = False
            cleaned['message_flag'] = ''
        elif preset == 'EXACT_FLAG':
            cleaned['match_type'] = 'EXACT'
            cleaned['use_message_flag'] = True
            if not (cleaned.get('message_flag') or '').strip():
                cleaned['message_flag'] = '#SMS'

        return cleaned


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    form = AutomationRuleAdminForm
    list_display = ('name', 'owner', 'event_type', 'match_type', 'action', 'use_message_flag', 'message_flag', 'priority', 'active')
    list_filter = ('event_type', 'match_type', 'action', 'active', 'use_message_flag')
    search_fields = ('name', 'description', 'owner__username', 'source_number', 'forward_to_number', 'message_flag')
    ordering = ('priority', 'id')
    filter_horizontal = ('source_groups', 'source_objects', 'target_numbers', 'target_groups', 'users')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(owner=request.user)

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.owner_id == request.user.id

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.owner_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.owner_id == request.user.id

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'owner' and not request.user.is_superuser:
            kwargs['queryset'] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if 'quick_preset' not in fields:
            fields.insert(0, 'quick_preset')
        if 'users' in fields:
            fields.remove('users')
        if not request.user.is_superuser and 'assign_to_users' in fields:
            fields.remove('assign_to_users')
        return fields

    def save_model(self, request, obj, form, change):
        if request.user.is_superuser:
            super().save_model(request, obj, form, change)
            return

        if change and obj.owner_id != request.user.id:
            raise PermissionDenied('Pravidlo může upravovat pouze jeho vlastník.')

        obj.owner = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        if not request.user.is_superuser:
            return

        selected_users = form.cleaned_data.get('assign_to_users')
        if selected_users is None:
            return

        rule = form.instance
        assigned_users = selected_users.exclude(pk=rule.owner_id)
        rule.users.set(assigned_users)
        if assigned_users.exists():
            self.message_user(
                request,
                f'Pravidlo přiřazeno uživatelům: {assigned_users.count()}. Vlastníkem zůstává {rule.owner.username}.',
            )


class OwnerRestrictedAdminMixin:
    owner_field_name = 'owner'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(**{self.owner_field_name: request.user})

    def _is_owner(self, request, obj):
        return getattr(obj, f'{self.owner_field_name}_id', None) == request.user.id

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self._is_owner(request, obj)

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self._is_owner(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self._is_owner(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == self.owner_field_name and not request.user.is_superuser:
            kwargs['queryset'] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if request.user.is_superuser:
            super().save_model(request, obj, form, change)
            return

        if change and not self._is_owner(request, obj):
            raise PermissionDenied('Záznam může upravovat pouze jeho vlastník.')

        setattr(obj, self.owner_field_name, request.user)
        super().save_model(request, obj, form, change)


@admin.register(DeviceObject)
class DeviceObjectAdmin(OwnerRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'object_label', 'owner', 'object_type', 'status_flag', 'active', 'updated_at')
    list_filter = ('object_type', 'status_flag', 'active')
    search_fields = ('name', 'object_label', 'description', 'owner__username', 'status_label')
    ordering = ('name', 'id')


@admin.register(IncomingEventLog)
class IncomingEventLogAdmin(OwnerRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ('created_at', 'owner', 'event_type', 'source_number', 'processed')
    list_filter = ('event_type', 'processed')
    search_fields = ('owner__username', 'source_number', 'result_summary')
    ordering = ('-created_at',)


@admin.register(OutgoingAction)
class OutgoingActionAdmin(OwnerRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ('created_at', 'owner', 'action_type', 'target_number', 'status')
    list_filter = ('action_type', 'status')
    search_fields = ('owner__username', 'target_number', 'payload_message')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        queryset = super(OwnerRestrictedAdminMixin, self).get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(Q(rule__owner=request.user) | Q(rule__isnull=True, owner=request.user)).distinct()

    def _is_owner(self, request, obj):
        if obj.rule_id:
            return obj.rule.owner_id == request.user.id
        return obj.owner_id == request.user.id

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name == 'rule':
            kwargs['queryset'] = AutomationRule.objects.filter(owner=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if request.user.is_superuser:
            super().save_model(request, obj, form, change)
            return

        if obj.rule_id and obj.rule.owner_id != request.user.id:
            raise PermissionDenied('Akci může spravovat pouze vlastník navázaného pravidla.')

        obj.owner = request.user
        super().save_model(request, obj, form, change)
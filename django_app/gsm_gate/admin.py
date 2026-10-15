# Admin rozhraní pro modely Group a PhoneNumber
# slouží k pohodlné správě přes Django admin a zobrazení důležitých polí

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group as AuthGroup
from django.contrib.auth.models import Permission, User
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
from dashboard.access import is_admin

admin.site.site_header = 'Správa GSM brány'
admin.site.site_title = 'Admin GSM brány'
admin.site.index_title = 'Administrace systému'

# Django auth.Group (role pro přihlášení/oprávnění - Jen čtení/Operátor/
# Admin/...) se v adminu jmenuje stejně jako appková dashboard.Group
# (skupiny telefonních čísel/příjemců), obojí "Skupiny" - matoucí, obě
# položky v postranním menu adminu nerozeznatelné. Přejmenování jen
# metadat (ne DB sloupec, žádná migrace potřeba), jde o standardní
# vestavěný model, nejde ho upravit v dashboard/models.py.
AuthGroup._meta.verbose_name = 'Uživatelská skupina'
AuthGroup._meta.verbose_name_plural = 'Uživatelské skupiny'


def approve_users(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    modeladmin.message_user(request, f'Schváleno uživatelů: {count}')


approve_users.short_description = 'Schválit vybrané uživatele (aktivovat účet)'


admin.site.unregister(User)


# Vlastníka čísla/skupiny je potřeba vidět přímo v "picker" výběrech
# (FilteredSelectMultiple) - jinak v adminu nejde poznat, komu položka patří,
# když ji chce superuser přiřadit/sdílet jinam.
class PhoneNumberMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        label = obj.number
        if obj.contact_label:
            label = f"{label} — {obj.contact_label}"
        owner_name = obj.owner.username if obj.owner_id else '—'
        return f"{label} (vlastník: {owner_name})"


class GroupMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        owner_name = obj.owner.username if obj.owner_id else '—'
        return f"{obj.name} (vlastník: {owner_name})"


PERMISSION_ACTION_LABELS = {
    'add': 'Přidat',
    'change': 'Upravit',
    'delete': 'Smazat',
    'view': 'Zobrazit',
}


class CleanPermissionMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Čitelný popisek místo výchozí "Can add Foo" (anglický sloveso +
    Permission.name zmrazené v DB v angličtině při prvním migrate, bez
    ohledu na LANGUAGE_CODE) - vezme sloveso z codename a přeloží ho,
    model jde přes content_type.name (to respektuje verbose_name z
    models.py, tedy už česky)."""

    def label_from_instance(self, obj):
        action, _, _ = obj.codename.partition('_')
        action_label = PERMISSION_ACTION_LABELS.get(action, action)
        return f'{obj.content_type.name} – {action_label}'


class CustomUserChangeForm(UserChangeForm):
    """Rozšíření o hromadné přiřazení existujících čísel/skupin (sdílení -
    viz PhoneNumber.users / Group.users) přímo z editace uživatele - typicky
    hned po schválení nového účtu, ať má okamžitě přístup k tomu, co
    potřebuje, bez ručního zaškrtávání jednoho po druhém na detailu
    každého čísla/skupiny. Stejný vzor jako assign_to_users u
    AutomationRuleAdminForm, jen v opačném směru (odtud se obsazuje
    reverzní M2M PhoneNumber.users / Group.users).

    Taky zpřehledňuje výchozí "Oprávnění uživatele" (user_permissions) -
    bez téhle úpravy appka nabízela i desítky nerelevantních oprávnění
    z vestavěných Django aplikací (admin, contenttypes, sessions) a každé
    bylo napůl v angličtině ("Can add"), napůl v češtině (název modelu).
    Skutečná správa práv ale stejně vede přes uživatelské skupiny (pole
    "Uživatelské skupiny" níže, viz role-a-opravneni.md) - tohle pole je
    jen pro výjimečné doladění jednotlivce nad rámec jeho skupin.

    Pole "groups" tu je přeznačené explicitně (včetně popisku widgetu),
    protože bez toho by se jmenovalo stejně jako appkové "Skupiny"
    (dashboard.Group = skupiny telefonních čísel) hned vedle - viz
    assigned_groups níže. Django totiž popisek widgetu FilteredSelectMultiple
    u M2M pole bere z verbose_name POLE "groups" (vždy "skupiny"), ne
    z verbose_name_plural modelu auth.Group (ten je přeznačený v admin.py
    při importu, ale na tohle konkrétní pole to nemá vliv)."""

    groups = forms.ModelMultipleChoiceField(
        label='Uživatelské skupiny',
        queryset=AuthGroup.objects.all().order_by('name'),
        required=False,
        help_text='Role pro přihlášení/oprávnění (Jen čtení, Operátor, Admin, ...) - NE skupiny telefonních čísel.',
        widget=admin.widgets.FilteredSelectMultiple('uživatelské skupiny', is_stacked=False),
    )

    user_permissions = CleanPermissionMultipleChoiceField(
        label='Oprávnění (výjimky nad rámec skupin)',
        queryset=Permission.objects.filter(
            content_type__app_label__in=['dashboard', 'auth'],
        ).select_related('content_type').order_by('content_type__model', 'codename'),
        required=False,
        help_text=(
            'Většinu práv přiřazuj přes uživatelské skupiny výše (Jen čtení / Operátor / Admin / ...), '
            'ne tady jednotlivě. Tohle pole je pro výjimečné doladění konkrétního uživatele nad rámec jeho skupin.'
        ),
        widget=admin.widgets.FilteredSelectMultiple('oprávnění', is_stacked=False),
    )

    assigned_phone_numbers = PhoneNumberMultipleChoiceField(
        label='Telefonní čísla',
        queryset=PhoneNumber.objects.all().select_related('owner').order_by('number'),
        required=False,
        help_text=(
            'Čísla, ke kterým bude mít uživatel přístup (sdílení). Předvyplněna jsou i čísla '
            'zděděná z přiřazených skupin níže - uložením se jejich přístup zapíše i sem přímo, '
            'takže číslo nezůstane "duplicitně" jen v jednom z polí.'
        ),
        widget=admin.widgets.FilteredSelectMultiple('Telefonní čísla', is_stacked=False),
    )
    assigned_groups = GroupMultipleChoiceField(
        label='Skupiny telefonních čísel',
        queryset=Group.objects.all().select_related('owner').order_by('name'),
        required=False,
        help_text='Skupiny telefonních čísel, ke kterým bude mít uživatel přístup (sdílení) - NE uživatelské skupiny/role.',
        widget=admin.widgets.FilteredSelectMultiple('skupiny telefonních čísel', is_stacked=False),
    )

    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            assigned_groups = self.instance.shared.all()
            self.fields['assigned_phone_numbers'].initial = PhoneNumber.objects.filter(
                Q(users=self.instance) | Q(groups__in=assigned_groups)
            ).distinct()
            self.fields['assigned_groups'].initial = assigned_groups


@admin.register(User)
class CustomUserAdmin(DjangoUserAdmin):
    form = CustomUserChangeForm
    list_filter = DjangoUserAdmin.list_filter + ('is_active',)
    actions = (approve_users,)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Přiřazené kontakty (sdílení)', {'fields': ('assigned_phone_numbers', 'assigned_groups')}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if 'assigned_phone_numbers' in form.cleaned_data:
            obj.shared_numbers.set(form.cleaned_data['assigned_phone_numbers'])
        if 'assigned_groups' in form.cleaned_data:
            obj.shared.set(form.cleaned_data['assigned_groups'])


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


# Funkce pro zobrazení všech skupin M2M v jednom sloupci (čísla mohou být
# v několika skupinách zároveň)
def groups_list(obj):
    return ", ".join([g.name for g in obj.groups.all()])
groups_list.short_description = "Skupiny čísel"


##################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Phone Numbers"
##################################################################################################
class PhoneNumberAdminForm(forms.ModelForm):
    groups = GroupMultipleChoiceField(
        label='Skupiny telefonních čísel',
        queryset=Group.objects.all().select_related('owner').order_by('name'),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('skupiny telefonních čísel', is_stacked=False),
    )

    class Meta:
        model = PhoneNumber
        fields = '__all__'


# Registrace modelu PhoneNumber do admin rozhraní django a další přdané funkce
@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    form = PhoneNumberAdminForm
    list_display = ('number', 'contact_name', 'role', 'description', 'active', 'owner', groups_list, users_list)
    list_filter = ('active', 'owner', 'groups', GroupAssignmentFilter)
    search_fields = ('number', 'description', 'first_name', 'last_name', 'role', 'owner__username', 'groups__name')
    filter_horizontal = ('users',)  # 'groups' má vlastní pole ve formuláři (popisek včetně vlastníka)
    raw_id_fields = ('owner',)  # místo neexistujícího 'user'
    ordering = ('number',)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('groups', 'users')
    fieldsets = (
        (None, {
            'fields': ('number', 'description', 'active', 'owner', 'groups', 'users')
        }),
        ('Kontaktní údaje', {
            'fields': ('first_name', 'last_name', 'role', 'note', 'contact_email')
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
    hidden_numbers = PhoneNumberMultipleChoiceField(
        label='Skrytá čísla',
        queryset=PhoneNumber.objects.none(),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('Skrytá čísla', is_stacked=False),
    )

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
            self.fields['hidden_numbers'].queryset = selected_group.phone_numbers.select_related('owner').order_by('number')
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
    list_display = ('user', 'allow_incoming_sms', 'delivery_reports', 'last_signal_quality', 'updated_at')
    list_filter = ('allow_incoming_sms', 'delivery_reports')
    search_fields = ('user__username',)


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

    source_groups = GroupMultipleChoiceField(
        label='Zdrojové skupiny',
        queryset=Group.objects.all().select_related('owner').order_by('name'),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('Zdrojové skupiny', is_stacked=False),
    )
    target_numbers = PhoneNumberMultipleChoiceField(
        label='Cílová čísla',
        queryset=PhoneNumber.objects.all().select_related('owner').order_by('number'),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('Cílová čísla', is_stacked=False),
    )
    target_groups = GroupMultipleChoiceField(
        label='Cílové skupiny',
        queryset=Group.objects.all().select_related('owner').order_by('name'),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple('Cílové skupiny', is_stacked=False),
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
    list_display = ('name', 'owner', 'event_type', 'match_type', 'action', 'use_message_flag', 'message_flag', 'priority', 'active', 'is_protected')
    list_filter = ('event_type', 'match_type', 'action', 'active', 'use_message_flag', 'is_protected')
    search_fields = ('name', 'description', 'owner__username', 'source_number', 'forward_to_number', 'message_flag')
    ordering = ('priority', 'id')
    # source_groups/target_numbers/target_groups mají vlastní pole ve
    # formuláři (AutomationRuleAdminForm) - FilteredSelectMultiple s popiskem
    # včetně vlastníka, takže tady už nejsou (byl by to no-op).
    filter_horizontal = ('source_objects', 'users')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_admin(request.user):
            return queryset
        return queryset.filter(owner=request.user)

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return obj.owner_id == request.user.id

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return obj.owner_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        # Chráněné pravidlo (is_protected) nejde smazat v běžné appce
        # (rule_edit/rule_delete ve views.py to odmítají natvrdo, bez
        # výjimky - tam ta ochrana reálně žije a zůstává nedotčená).
        # V Django Adminu ji admin/superuser smí smazat - jinak by šlo
        # kaskádově smazat jen uživatele, kteří žádné takové pravidlo
        # nemají (get_or_create_default_security_notification_rule ho
        # založí téměř každému), a šlo by ho tu stejně libovolně upravit,
        # jen ne smazat - nekonzistentní asymetrie bez reálného přínosu.
        if obj is not None and obj.is_protected and not is_admin(request.user):
            return False
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return obj.owner_id == request.user.id

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'owner' and not is_admin(request.user):
            kwargs['queryset'] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if 'quick_preset' not in fields:
            fields.insert(0, 'quick_preset')
        if 'users' in fields:
            fields.remove('users')
        if not is_admin(request.user) and 'assign_to_users' in fields:
            fields.remove('assign_to_users')
        return fields

    def save_model(self, request, obj, form, change):
        if is_admin(request.user):
            super().save_model(request, obj, form, change)
            return

        if change and obj.owner_id != request.user.id:
            raise PermissionDenied('Pravidlo může upravovat pouze jeho vlastník.')

        obj.owner = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        if not is_admin(request.user):
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
        if is_admin(request.user):
            return queryset
        return queryset.filter(**{self.owner_field_name: request.user})

    def _is_owner(self, request, obj):
        return getattr(obj, f'{self.owner_field_name}_id', None) == request.user.id

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return self._is_owner(request, obj)

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return self._is_owner(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or is_admin(request.user):
            return True
        return self._is_owner(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == self.owner_field_name and not is_admin(request.user):
            kwargs['queryset'] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if is_admin(request.user):
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
    filter_horizontal = ('users',)


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
        if is_admin(request.user):
            return queryset
        return queryset.filter(Q(rule__owner=request.user) | Q(rule__isnull=True, owner=request.user)).distinct()

    def _is_owner(self, request, obj):
        if obj.rule_id:
            return obj.rule.owner_id == request.user.id
        return obj.owner_id == request.user.id

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not is_admin(request.user) and db_field.name == 'rule':
            kwargs['queryset'] = AutomationRule.objects.filter(owner=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if is_admin(request.user):
            super().save_model(request, obj, form, change)
            return

        if obj.rule_id and obj.rule.owner_id != request.user.id:
            raise PermissionDenied('Akci může spravovat pouze vlastník navázaného pravidla.')

        obj.owner = request.user
        super().save_model(request, obj, form, change)
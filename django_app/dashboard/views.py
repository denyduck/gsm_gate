# logika pro zobrazení dashboardu a správu čísel
# jinja2 šablony jsou v django_app/dashboard/templates/dashboard/

import io
import json
import os
import tempfile
from urllib import error as urllib_error
from urllib import request as urllib_request

import qrcode
from django import forms
from django.core import management
from django.core.exceptions import PermissionDenied
from django.forms import modelform_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    BlockedNumber,
    PhoneNumber,
    Group,
    DeviceObject,
    DeviceObjectApiCredential,
    GatewaySettings,
    AutomationRule,
    IncomingEventLog,
    OutgoingAction,
    SelfTestRun,
)
from .forms import (
    BlockedNumberForm,
    PhoneNumberForm,
    GroupForm,
    BulkNumberGroupAssignForm,
    GatewaySettingsForm,
    AutomationRuleForm,
    IncomingEventSimulationForm,
)
from .services import backup as backup_service
from .services import reset as reset_service
from .services import selftest as selftest_service
from .services import telemetry as telemetry_service
from .services.rules_engine import (
    get_or_create_default_security_notification_rule,
    get_security_rule,
    normalize_phone_number,
    process_incoming_event,
)


# Zobrazení dashboardu s čísly uživatele
@login_required
def dashboard_view(request):
    # vyber všechna čísla, kde je uživatel v uživatelích
    numbers = PhoneNumber.objects.filter(users=request.user).prefetch_related('groups').order_by('number')
    # vyber všechny skupiny, kde je uživatel vlastníkem nebo je alespon v uživatelích
    groups = Group.objects.filter(users=request.user).prefetch_related('phone_numbers').order_by('name')
    objects = DeviceObject.objects.filter(owner=request.user).order_by('name', 'id')

    editable_number_ids = list(numbers.values_list('id', flat=True))
    deletable_number_ids = editable_number_ids
    editable_group_ids = list(groups.values_list('id', flat=True))
    deletable_group_ids = editable_group_ids
    object_ids = list(objects.values_list('id', flat=True))
    editable_object_ids = object_ids
    deletable_object_ids = object_ids
    # předání čísel a skupin do šablony
    
    active_numbers_count = numbers.filter(active=True).count()
    rules = AutomationRule.objects.filter(owner=request.user).order_by('name')
    rules_count = rules.count()
    recent_logs = IncomingEventLog.objects.filter(owner=request.user).order_by('-created_at')[:50]
    logs_count = IncomingEventLog.objects.filter(owner=request.user).count()
    objects_count = objects.count()

    context = {
        'numbers': numbers,
        'groups': groups,
        'objects': objects,
        'active_numbers_count': active_numbers_count,
        'rules': rules,
        'rules_count': rules_count,
        'recent_logs': recent_logs,
        'logs_count': logs_count,
        'objects_count': objects_count,
        'editable_number_ids': editable_number_ids,
        'deletable_number_ids': deletable_number_ids,
        'editable_group_ids': editable_group_ids,
        'deletable_group_ids': deletable_group_ids,
        'editable_object_ids': editable_object_ids,
        'deletable_object_ids': deletable_object_ids,
        'can_add_number': request.user.has_perm('dashboard.add_phonenumber'),
        'can_bulk_add_numbers': request.user.has_perm('dashboard.add_phonenumber'),
        'can_view_number': request.user.has_perm('dashboard.view_phonenumber'),
        'can_change_number': request.user.has_perm('dashboard.change_phonenumber'),
        'can_delete_number': request.user.has_perm('dashboard.delete_phonenumber'),
        'can_add_group': request.user.has_perm('dashboard.add_group'),
        'can_view_group': request.user.has_perm('dashboard.view_group'),
        'can_change_group': request.user.has_perm('dashboard.change_group'),
        'can_delete_group': request.user.has_perm('dashboard.delete_group'),
        'can_view_rules': request.user.has_perm('dashboard.view_automationrule'),
        'can_add_rule': request.user.has_perm('dashboard.add_automationrule'),
        'can_change_rule': request.user.has_perm('dashboard.change_automationrule'),
        'can_delete_rule': request.user.has_perm('dashboard.delete_automationrule'),
        'can_simulate_events': request.user.has_perm('dashboard.add_incomingeventlog'),
        'can_view_logs': request.user.has_perm('dashboard.view_incomingeventlog'),
        'can_view_outgoing_actions': request.user.has_perm('dashboard.view_outgoingaction'),
        'can_view_gateway_status': request.user.has_perm('dashboard.view_gatewaysettings'),
        'can_change_gateway_settings': request.user.has_perm('dashboard.change_gatewaysettings'),
        'can_view_object': request.user.has_perm('dashboard.view_deviceobject'),
        'can_add_object': request.user.has_perm('dashboard.add_deviceobject'),
        'can_change_object': request.user.has_perm('dashboard.change_deviceobject'),
        'can_delete_object': request.user.has_perm('dashboard.delete_deviceobject'),
    }

    return render(request, 'dashboard/dashboard.html', context)


######################################################################################################
#CRUD OPERACE S ČÍSLY
######################################################################################################
# Vytvoření nového čísla
@login_required
@permission_required('dashboard.add_phonenumber', raise_exception=True)
def number_create(request):
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST, user=request.user)
        if form.is_valid():
            number = form.save(commit=False)  # nevytváří hned v DB
            number.owner = request.user       # přiřadíme vlastníka
            number.save()
            form.save_m2m()                   # uloží M2M pole (users, groups)

            # přidat vlastníka do uživatelů
            if request.user not in number.users.all():
                number.users.add(request.user)

            return redirect('dashboard')
    else:
        form = PhoneNumberForm(user=request.user)
    return render(request, 'dashboard/number_form.html', {'form': form})


@login_required
@permission_required('dashboard.add_phonenumber', raise_exception=True)
def number_bulk_add(request):
    if request.method == 'POST':
        form = BulkNumberGroupAssignForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            parsed_numbers = form.cleaned_data['parsed_numbers']
            operation = form.cleaned_data['operation']
            selected_groups = list(form.cleaned_data['groups'])
            create_missing = form.cleaned_data.get('create_missing', False)
            group_ids = [group.id for group in selected_groups]

            created_count = 0
            processed_existing = 0
            skipped_missing = 0
            changed_relations = 0
            changed_active_state = 0

            for normalized_number in parsed_numbers:
                number = PhoneNumber.objects.filter(users=request.user, number=normalized_number).first()

                if number is None:
                    if operation == 'ADD_GROUPS' and create_missing:
                        number = PhoneNumber.objects.create(
                            owner=request.user,
                            number=normalized_number,
                            description='',
                            active=True,
                        )
                        created_count += 1
                    else:
                        skipped_missing += 1
                        continue

                processed_existing += 1

                if not number.users.filter(pk=request.user.pk).exists():
                    number.users.add(request.user)

                if operation == 'ADD_GROUPS':
                    existing_links = number.groups.filter(id__in=group_ids).count()
                    number.groups.add(*selected_groups)
                    changed_relations += max(0, len(group_ids) - existing_links)

                elif operation == 'REMOVE_GROUPS':
                    existing_links = number.groups.filter(id__in=group_ids).count()
                    number.groups.remove(*selected_groups)
                    changed_relations += existing_links

                elif operation == 'REPLACE_GROUPS':
                    before_ids = set(number.groups.values_list('id', flat=True))
                    target_ids = set(group_ids)
                    number.groups.set(selected_groups)
                    changed_relations += len(before_ids.symmetric_difference(target_ids))

                elif operation == 'SET_ACTIVE':
                    if not number.active:
                        number.active = True
                        number.save(update_fields=['active'])
                        changed_active_state += 1

                elif operation == 'SET_INACTIVE':
                    if number.active:
                        number.active = False
                        number.save(update_fields=['active'])
                        changed_active_state += 1

            operation_label = dict(form.fields['operation'].choices).get(operation, operation)

            if operation in ('SET_ACTIVE', 'SET_INACTIVE'):
                detail_summary = f'změněný stav u {changed_active_state} čísel'
            else:
                detail_summary = f'změněné vazby ke skupinám: {changed_relations}'

            messages.success(
                request,
                (
                    f'Hromadná úprava dokončena ({operation_label}): zadaných {len(parsed_numbers)} čísel, '
                    f'zpracovaných {processed_existing}, nově vytvořených {created_count}, '
                    f'přeskočených (nenalezených) {skipped_missing}, {detail_summary}.'
                ),
            )
            return redirect('number_bulk_add')
    else:
        form = BulkNumberGroupAssignForm(user=request.user)

    return render(request, 'dashboard/number_bulk_add.html', {'form': form})


@login_required
@permission_required('dashboard.add_phonenumber', raise_exception=True)
def number_bulk_csv_template(request):
    csv_content = (
        'phone_number,description\n'
        '+420777111222,Obchod\n'
        '+420777111333,Servis\n'
        '00420777111444,Pohotovost\n'
    )
    response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="bulk_numbers_template.csv"'
    return response

# Úprava existujícího čísla
@login_required
@permission_required('dashboard.change_phonenumber', raise_exception=True)
def number_update(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, users=request.user)
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST, instance=number, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = PhoneNumberForm(instance=number, user=request.user)
    return render(request, 'dashboard/number_form.html', {'form': form})

# Smazání čísla
@login_required
@permission_required('dashboard.delete_phonenumber', raise_exception=True)
def number_delete(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, users=request.user)
    if request.method == 'POST':
        number.delete()
        return redirect('dashboard')
    return render(request, 'dashboard/number_confirm_delete.html', {'number': number})


@login_required
@permission_required('dashboard.view_phonenumber', raise_exception=True)
def number_detail(request, pk):
    number = get_object_or_404(
        PhoneNumber.objects.prefetch_related('groups', 'users'),
        pk=pk,
        users=request.user,
    )

    related_rules_as_target = AutomationRule.objects.filter(
        owner=request.user,
        target_numbers=number,
    ).order_by('priority', 'id')

    related_rules_as_source = AutomationRule.objects.filter(
        owner=request.user,
        source_number=number.number,
    ).order_by('priority', 'id')

    related_logs = IncomingEventLog.objects.filter(
        owner=request.user,
        source_number=number.number,
    ).order_by('-created_at')[:20]

    related_actions = OutgoingAction.objects.filter(
        owner=request.user,
        target_number=number.number,
    ).select_related('rule', 'event_log').order_by('-created_at')[:20]

    context = {
        'number': number,
        'related_rules_as_target': related_rules_as_target,
        'related_rules_as_source': related_rules_as_source,
        'related_logs': related_logs,
        'related_actions': related_actions,
        'can_change_number': request.user.has_perm('dashboard.change_phonenumber'),
        'can_delete_number': request.user.has_perm('dashboard.delete_phonenumber'),
    }
    return render(request, 'dashboard/number_detail.html', context)

######################################################################################################
#CRUD OPERACE SE SKUPINAMI
######################################################################################################
# Vytvoření nové skupiny
@login_required
@permission_required('dashboard.add_group', raise_exception=True)
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)

        if form.is_valid():
            group = form.save(commit=False)
            group.owner = request.user
            group.save()
            # přidat vlastníka do uživatelů
            group.users.add(request.user)
            return redirect('dashboard')
    else:
        form = GroupForm()
    return render(request, 'dashboard/group_form.html', {'form': form})

# Úprava existující skupiny
@login_required
@permission_required('dashboard.change_group', raise_exception=True)
def group_update(request, pk):
    group = get_object_or_404(Group, pk=pk, users=request.user)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = GroupForm(instance=group)
    return render(request, 'dashboard/group_form.html', {'form': form})

# Smazání skupiny
@login_required
@permission_required('dashboard.delete_group', raise_exception=True)
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk, users=request.user)
    if request.method == 'POST':
        group.delete()
        return redirect('dashboard')
    return render(request, 'dashboard/group_confirm_delete.html', {'group': group})


@login_required
@permission_required('dashboard.view_group', raise_exception=True)
def group_detail(request, pk):
    group = get_object_or_404(
        Group.objects.prefetch_related('phone_numbers', 'users'),
        pk=pk,
        users=request.user,
    )

    source_rules = AutomationRule.objects.filter(
        owner=request.user,
        source_groups=group,
    ).order_by('priority', 'id')

    if not source_rules.exists():
        source_rules = AutomationRule.objects.filter(
            owner=request.user,
            source_group=group,
        ).order_by('priority', 'id')

    target_rules = AutomationRule.objects.filter(
        owner=request.user,
        target_groups=group,
    ).order_by('priority', 'id')

    members = group.phone_numbers.filter(users=request.user).order_by('number')

    related_actions = OutgoingAction.objects.filter(
        owner=request.user,
        rule__target_groups=group,
    ).select_related('rule', 'event_log').order_by('-created_at')[:20]

    context = {
        'group': group,
        'members': members,
        'source_rules': source_rules,
        'target_rules': target_rules,
        'related_actions': related_actions,
        'can_change_group': request.user.has_perm('dashboard.change_group'),
        'can_delete_group': request.user.has_perm('dashboard.delete_group'),
    }
    return render(request, 'dashboard/group_detail.html', context)


@login_required
@permission_required('dashboard.view_deviceobject', raise_exception=True)
def device_objects_list_view(request):
    objects = DeviceObject.objects.filter(owner=request.user).order_by('name', 'id')
    object_ids = list(objects.values_list('id', flat=True))
    context = {
        'objects': objects,
        'can_view_object': request.user.has_perm('dashboard.view_deviceobject'),
        'can_add_object': request.user.has_perm('dashboard.add_deviceobject'),
        'can_change_object': request.user.has_perm('dashboard.change_deviceobject'),
        'can_delete_object': request.user.has_perm('dashboard.delete_deviceobject'),
        'editable_object_ids': object_ids,
        'deletable_object_ids': object_ids,
    }
    return render(request, 'dashboard/device_objects_list.html', context)


@login_required
@permission_required('dashboard.add_deviceobject', raise_exception=True)
def device_object_create(request):
    DeviceObjectForm = modelform_factory(
        DeviceObject,
        fields=['name', 'object_label', 'object_type', 'icon', 'status_flag', 'status_label', 'active', 'description', 'specification'],
        widgets={
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'object_label': forms.TextInput(attrs={'class': 'form-control'}),
            'object_type': forms.Select(attrs={'class': 'form-select'}),
            'status_flag': forms.Select(attrs={'class': 'form-select'}),
            'status_label': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'specification': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        },
    )

    if request.method == 'POST':
        form = DeviceObjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            DeviceObjectApiCredential.objects.get_or_create(
                device_object=obj,
                defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
            )
            messages.success(request, 'Objekt zařízení byl vytvořen.')
            return redirect('device_object_detail', pk=obj.pk)
    else:
        form = DeviceObjectForm()

    return render(request, 'dashboard/device_object_form.html', {'form': form, 'title': 'Nový objekt zařízení'})


@login_required
@permission_required('dashboard.view_deviceobject', raise_exception=True)
def device_object_detail(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    api_credential, _ = DeviceObjectApiCredential.objects.get_or_create(
        device_object=obj,
        defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
    )

    context = {
        'obj': obj,
        'api_credential': api_credential,
        'api_ingest_url': request.build_absolute_uri(reverse('device_event_ingest_api')),
        'can_change_object': request.user.has_perm('dashboard.change_deviceobject'),
        'can_delete_object': request.user.has_perm('dashboard.delete_deviceobject'),
    }
    return render(request, 'dashboard/device_object_detail.html', context)


@login_required
@permission_required('dashboard.change_deviceobject', raise_exception=True)
def device_object_update(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    DeviceObjectForm = modelform_factory(
        DeviceObject,
        fields=['name', 'object_label', 'object_type', 'icon', 'status_flag', 'status_label', 'active', 'description', 'specification'],
        widgets={
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'object_label': forms.TextInput(attrs={'class': 'form-control'}),
            'object_type': forms.Select(attrs={'class': 'form-select'}),
            'status_flag': forms.Select(attrs={'class': 'form-select'}),
            'status_label': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'specification': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        },
    )

    if request.method == 'POST':
        form = DeviceObjectForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Objekt zařízení byl upraven.')
            return redirect('device_object_detail', pk=obj.pk)
    else:
        form = DeviceObjectForm(instance=obj)

    return render(request, 'dashboard/device_object_form.html', {'form': form, 'title': 'Úprava objektu zařízení'})


@login_required
@permission_required('dashboard.delete_deviceobject', raise_exception=True)
def device_object_delete(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Objekt zařízení byl smazán.')
        return redirect('device_objects_list')
    return render(request, 'dashboard/device_object_confirm_delete.html', {'obj': obj})


@login_required
@permission_required('dashboard.change_deviceobject', raise_exception=True)
def device_object_regenerate_api_key(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    credential, _ = DeviceObjectApiCredential.objects.get_or_create(
        device_object=obj,
        defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
    )
    credential.token = DeviceObjectApiCredential.generate_token()
    credential.active = True
    credential.save(update_fields=['token', 'active', 'updated_at'])
    messages.success(request, 'API klíč byl vygenerován znovu.')
    return redirect('device_object_detail', pk=obj.pk)


@login_required
@permission_required('dashboard.view_deviceobject', raise_exception=True)
def device_object_export_config(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    credential, _ = DeviceObjectApiCredential.objects.get_or_create(
        device_object=obj,
        defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
    )

    payload = {
        'device_object_id': obj.id,
        'device_object_name': obj.name,
        'ingest_url': request.build_absolute_uri(reverse('device_event_ingest_api')),
        'headers': {'X-Device-Token': credential.token},
        'example_payload': {
            'event_type': 'API',
            'source_number': str(obj.id),
            'message_body': obj.status_label or 'test event',
        },
    }

    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type='application/json; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="device_object_{obj.id}_config.json"'
    return response


@login_required
@permission_required('dashboard.view_deviceobject', raise_exception=True)
@require_http_methods(['POST'])
def device_object_test_call(request, pk):
    """Skutečně zavolá reálný ingest endpoint reálným HTTP požadavkem se
    skutečným tokenem objektu - ověří tak celou cestu (token, síť, ALLOWED_HOSTS
    apod.), ne jen interní logiku vyhodnocení pravidel."""
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    credential, _ = DeviceObjectApiCredential.objects.get_or_create(
        device_object=obj,
        defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
    )

    test_message = request.POST.get('message', '').strip() or f'Testovací požadavek z detailu objektu „{obj.name}“.'
    payload = json.dumps({
        'event_type': 'API',
        'source_number': str(obj.id),
        'message_body': test_message,
    }).encode('utf-8')

    ingest_url = request.build_absolute_uri(reverse('device_event_ingest_api'))
    req = urllib_request.Request(
        ingest_url,
        data=payload,
        headers={'Content-Type': 'application/json', 'X-Device-Token': credential.token},
        method='POST',
    )
    try:
        with urllib_request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            messages.success(request, f'Testovací požadavek proběhl úspěšně (HTTP {resp.status}): {body}')
    except urllib_error.HTTPError as exc:
        body = exc.read().decode('utf-8')
        messages.error(request, f'Testovací požadavek selhal (HTTP {exc.code}): {body}')
    except Exception as exc:
        messages.error(request, f'Testovací požadavek selhal: {exc}')

    return redirect('device_object_detail', pk=obj.pk)


@login_required
@permission_required('dashboard.view_deviceobject', raise_exception=True)
def device_object_qr_code(request, pk):
    obj = get_object_or_404(DeviceObject, pk=pk, owner=request.user)
    credential, _ = DeviceObjectApiCredential.objects.get_or_create(
        device_object=obj,
        defaults={'token': DeviceObjectApiCredential.generate_token(), 'active': True},
    )

    trigger_url = request.build_absolute_uri(reverse('device_object_trigger', args=[credential.token]))

    img = qrcode.make(trigger_url, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')

    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Cache-Control'] = 'no-store'
    return response


def device_object_trigger(request, token):
    """Veřejný (bez přihlášení) spouštěč pro naskenovaný QR kód / fyzické
    tlačítko - token v URL slouží jako sdílené tajemství (obdoba bearer
    tokenu), takže odkaz/QR kód je potřeba chránit jako heslo."""
    credential = DeviceObjectApiCredential.objects.filter(token=token, active=True).select_related('device_object__owner').first()

    if credential is None:
        return render(request, 'dashboard/device_object_trigger_result.html', {'ok': False}, status=404)

    obj = credential.device_object
    message_body = request.GET.get('msg', '').strip() or f'Spuštěno naskenováním QR kódu objektu „{obj.name}“.'

    event_log, matched_count, queued_count = process_incoming_event(
        user=obj.owner,
        event_type='API',
        source_number=str(obj.id),
        message_body=message_body,
        source_device_object=obj,
    )

    credential.last_used_at = event_log.created_at
    credential.save(update_fields=['last_used_at'])

    context = {
        'ok': True,
        'obj': obj,
        'matched_count': matched_count,
        'queued_count': queued_count,
        'created_at': event_log.created_at,
    }
    return render(request, 'dashboard/device_object_trigger_result.html', context)


@csrf_exempt
@require_http_methods(['POST'])
def device_event_ingest_api(request):
    token = request.headers.get('X-Device-Token', '').strip()
    if not token:
        return JsonResponse({'ok': False, 'error': 'Missing X-Device-Token header'}, status=401)

    credential = DeviceObjectApiCredential.objects.filter(token=token, active=True).select_related('device_object__owner').first()
    if credential is None:
        return JsonResponse({'ok': False, 'error': 'Invalid API token'}, status=401)

    try:
        payload = json.loads(request.body.decode('utf-8') if request.body else '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload'}, status=400)

    event_type = str(payload.get('event_type') or 'API').upper()
    if event_type not in ('SMS', 'CALL', 'API'):
        event_type = 'API'

    source_number = str(payload.get('source_number') or credential.device_object.id)
    message_body = str(payload.get('message_body') or '')

    event_log, matched_count, queued_count = process_incoming_event(
        user=credential.device_object.owner,
        event_type=event_type,
        source_number=source_number,
        message_body=message_body,
        source_device_object=credential.device_object,
    )

    credential.last_used_at = event_log.created_at
    credential.save(update_fields=['last_used_at'])

    return JsonResponse(
        {
            'ok': True,
            'event_log_id': event_log.id,
            'matched_rules': matched_count,
            'queued_actions': queued_count,
        },
        status=201,
    )


@login_required
@permission_required('dashboard.view_gatewaysettings', raise_exception=True)
def gateway_signal_api(request):
    settings_obj = GatewaySettings.objects.filter(user=request.user).first()
    if settings_obj is None:
        return JsonResponse({'ok': False})

    return JsonResponse({
        'ok': True,
        'quality': settings_obj.last_signal_quality,
        'label': settings_obj.signal_label,
        'dbm': settings_obj.signal_dbm,
        'checked_at': settings_obj.last_signal_checked_at.isoformat() if settings_obj.last_signal_checked_at else None,
    })


@login_required
@permission_required('dashboard.view_gatewaysettings', raise_exception=True)
def gateway_status_view(request):
    settings_obj, _ = GatewaySettings.objects.get_or_create(user=request.user)
    numbers_count = PhoneNumber.objects.filter(users=request.user).count()
    groups_count = Group.objects.filter(users=request.user).count()

    context = {
        'gateway_settings': settings_obj,
        'numbers_count': numbers_count,
        'groups_count': groups_count,
    }
    return render(request, 'dashboard/gateway_status.html', context)


@login_required
@permission_required('dashboard.change_gatewaysettings', raise_exception=True)
def gateway_settings_view(request):
    settings_obj, _ = GatewaySettings.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = GatewaySettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            return redirect('gateway_settings')
    else:
        form = GatewaySettingsForm(instance=settings_obj)

    return render(request, 'dashboard/gateway_settings.html', {'form': form})


@login_required
@permission_required('dashboard.view_automationrule', raise_exception=True)
def rules_list_view(request):
    get_or_create_default_security_notification_rule(request.user)
    rules = AutomationRule.objects.filter(owner=request.user).prefetch_related('target_numbers', 'target_groups').order_by('priority', 'id')
    unprotected_rule_ids = list(rules.exclude(is_protected=True).values_list('id', flat=True))
    return render(
        request,
        'dashboard/rules_list.html',
        {
            'rules': rules,
            'editable_rule_ids': unprotected_rule_ids,
            'deletable_rule_ids': unprotected_rule_ids,
            'security_rule': get_security_rule(request.user),
            'can_view_rule': request.user.has_perm('dashboard.view_automationrule'),
            'can_add_rule': request.user.has_perm('dashboard.add_automationrule'),
            'can_change_rule': request.user.has_perm('dashboard.change_automationrule'),
            'can_delete_rule': request.user.has_perm('dashboard.delete_automationrule'),
            'can_simulate_events': request.user.has_perm('dashboard.add_incomingeventlog'),
            'can_view_logs': request.user.has_perm('dashboard.view_incomingeventlog'),
            'can_view_outgoing_actions': request.user.has_perm('dashboard.view_outgoingaction'),
        },
    )


@login_required
@permission_required('dashboard.view_automationrule', raise_exception=True)
def rule_detail(request, pk):
    rule = get_object_or_404(
        AutomationRule.objects.filter(owner=request.user)
        .prefetch_related('source_groups', 'target_numbers', 'target_groups'),
        pk=pk,
    )

    recent_actions = OutgoingAction.objects.filter(
        owner=request.user,
        rule=rule,
    ).select_related('event_log').order_by('-created_at')[:30]

    source_logs = IncomingEventLog.objects.filter(owner=request.user)
    if rule.match_type == 'EXACT' and rule.source_number:
        source_logs = source_logs.filter(source_number=rule.source_number)
    source_logs = source_logs.order_by('-created_at')[:30]

    context = {
        'rule': rule,
        'recent_actions': recent_actions,
        'source_logs': source_logs,
        'can_simulate_events': request.user.has_perm('dashboard.add_incomingeventlog'),
        'can_change_rule': request.user.has_perm('dashboard.change_automationrule'),
        'can_delete_rule': request.user.has_perm('dashboard.delete_automationrule'),
    }
    return render(request, 'dashboard/rule_detail.html', context)


@login_required
@permission_required('dashboard.add_automationrule', raise_exception=True)
def rule_create(request):
    if request.method == 'POST':
        form = AutomationRuleForm(request.POST, user=request.user)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.owner = request.user
            rule.save()
            form.save_m2m()
            messages.success(request, 'Pravidlo bylo vytvořeno.')
            return redirect('rules_list')
    else:
        form = AutomationRuleForm(user=request.user)

    return render(request, 'dashboard/rule_form.html', {'form': form, 'title': 'Nové pravidlo'})


@login_required
@permission_required('dashboard.change_automationrule', raise_exception=True)
def rule_update(request, pk):
    rule = get_object_or_404(AutomationRule, pk=pk, owner=request.user)

    if rule.is_protected:
        messages.error(request, 'Chráněné systémové pravidlo lze upravit jen přes Django Admin.')
        return redirect('rules_list')

    if request.method == 'POST':
        form = AutomationRuleForm(request.POST, instance=rule, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pravidlo bylo upraveno.')
            return redirect('rules_list')
    else:
        form = AutomationRuleForm(instance=rule, user=request.user)

    return render(request, 'dashboard/rule_form.html', {'form': form, 'title': 'Úprava pravidla'})


@login_required
@permission_required('dashboard.delete_automationrule', raise_exception=True)
def rule_delete(request, pk):
    rule = get_object_or_404(AutomationRule, pk=pk, owner=request.user)

    if rule.is_protected:
        messages.error(request, 'Chráněné systémové pravidlo nejde smazat.')
        return redirect('rules_list')

    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Pravidlo bylo smazáno.')
        return redirect('rules_list')

    return render(request, 'dashboard/rule_confirm_delete.html', {'rule': rule})


@login_required
@permission_required('dashboard.add_incomingeventlog', raise_exception=True)
def incoming_simulator_view(request):
    latest_log = None
    generated_actions = OutgoingAction.objects.none()

    if request.method == 'POST':
        form = IncomingEventSimulationForm(request.POST)
        if form.is_valid():
            latest_log, matched_count, queued_count = process_incoming_event(
                user=request.user,
                event_type=form.cleaned_data['event_type'],
                source_number=form.cleaned_data['source_number'],
                message_body=form.cleaned_data['message_body'],
            )
            generated_actions = latest_log.actions.all()
            messages.success(
                request,
                f'Událost zpracována. Odpovídající pravidla: {matched_count}, akce ve frontě: {queued_count}.',
            )
    else:
        initial_data = {}
        event_type = request.GET.get('event_type', '').strip().upper()
        source_number = request.GET.get('source_number', '').strip()
        message_body = request.GET.get('message_body', '').strip()

        if event_type in ('SMS', 'CALL'):
            initial_data['event_type'] = event_type
        if source_number:
            initial_data['source_number'] = source_number
        if message_body:
            initial_data['message_body'] = message_body

        form = IncomingEventSimulationForm(initial=initial_data)

    recent_logs = IncomingEventLog.objects.filter(owner=request.user).prefetch_related('actions')[:20]
    context = {
        'form': form,
        'latest_log': latest_log,
        'generated_actions': generated_actions,
        'recent_logs': recent_logs,
    }
    return render(request, 'dashboard/incoming_simulator.html', context)


@login_required
@permission_required('dashboard.view_incomingeventlog', raise_exception=True)
def event_logs_view(request):
    logs = IncomingEventLog.objects.filter(owner=request.user).prefetch_related('actions')[:100]
    return render(request, 'dashboard/event_logs.html', {'logs': logs})


@login_required
@permission_required('dashboard.view_blockednumber', raise_exception=True)
def blocked_numbers_view(request):
    if request.method == 'POST':
        form = BlockedNumberForm(request.POST)
        if form.is_valid():
            number = normalize_phone_number(form.cleaned_data['number'])
            if number:
                BlockedNumber.objects.update_or_create(
                    owner=request.user,
                    number=number,
                    defaults={'reason': form.cleaned_data['reason'], 'expires_at': None},
                )
                messages.success(request, f'Číslo {number} bylo zablokováno.')
            return redirect('blocked_numbers')
    else:
        form = BlockedNumberForm()

    numbers = BlockedNumber.objects.filter(owner=request.user)
    security_rule = get_security_rule(request.user)
    context = {
        'form': form,
        'numbers': numbers,
        'security_rule': security_rule,
    }
    return render(request, 'dashboard/blocked_numbers.html', context)


@login_required
@permission_required('dashboard.delete_blockednumber', raise_exception=True)
def blocked_number_delete(request, pk):
    blocked = get_object_or_404(BlockedNumber, pk=pk, owner=request.user)
    if request.method == 'POST':
        number = blocked.number
        blocked.delete()
        messages.success(request, f'Číslo {number} bylo odblokováno.')
    return redirect('blocked_numbers')


@login_required
@permission_required('dashboard.view_incomingeventlog', raise_exception=True)
def event_log_detail_view(request, pk):
    log = get_object_or_404(
        IncomingEventLog.objects.filter(owner=request.user),
        pk=pk,
    )

    all_actions_qs = OutgoingAction.objects.filter(owner=request.user, event_log=log).select_related('rule').order_by('-created_at')

    active_status_filter = (request.GET.get('status') or '').strip().upper()
    allowed_statuses = {'PENDING', 'SENT', 'FAILED'}
    if active_status_filter not in allowed_statuses:
        active_status_filter = ''

    actions_qs = all_actions_qs
    if active_status_filter:
        actions_qs = actions_qs.filter(status=active_status_filter)

    status_counts = {
        'ALL': all_actions_qs.count(),
        'PENDING': all_actions_qs.filter(status='PENDING').count(),
        'SENT': all_actions_qs.filter(status='SENT').count(),
        'FAILED': all_actions_qs.filter(status='FAILED').count(),
    }

    actions = list(actions_qs)
    flag_map = {
        'NOTIFY_NUM': 'Notifikace na cílová čísla',
        'NOTIFY_GRP': 'Notifikace na cílové skupiny',
        'FORWARD': 'Předání na číslo',
    }
    for action in actions:
        action.flag_label = flag_map.get(action.rule.action, '') if action.rule else ''

    context = {
        'log': log,
        'actions': actions,
        'status_counts': status_counts,
        'active_status_filter': active_status_filter,
    }
    return render(request, 'dashboard/event_log_detail.html', context)


@login_required
@permission_required('dashboard.view_outgoingaction', raise_exception=True)
def outgoing_actions_view(request):
    actions = OutgoingAction.objects.filter(owner=request.user).select_related('event_log', 'rule')[:200]
    gateway_settings = GatewaySettings.objects.filter(user=request.user).first()
    context = {
        'actions': actions,
        'gateway_settings': gateway_settings,
    }
    return render(request, 'dashboard/outgoing_actions.html', context)


# Zálohování - export/import dat pomocí Django dumpdata/loaddata (osvědčený
# formát, žádná vlastní serializace, sdíleno s management příkazem
# export_backup pro plánované zálohy - viz services/backup.py). Jen pro
# superusera - dotýká se dat napříč všemi uživateli, ne jen vlastníka.

@login_required
def backup_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Zálohování je dostupné jen pro superusera.')

    context = {
        'reset_categories': [(key, label) for key, (label, _func) in reset_service.RESET_ACTIONS.items()],
        'reset_confirm_phrase': reset_service.CONFIRM_PHRASE,
    }
    return render(request, 'dashboard/backup.html', context)


@login_required
def backup_export(request, kind):
    if not request.user.is_superuser:
        raise PermissionDenied('Zálohování je dostupné jen pro superusera.')

    model_labels = backup_service.MODEL_SETS.get(kind)
    if model_labels is None:
        raise Http404('Neznámý typ zálohy.')

    content = backup_service.dump_models(model_labels)
    filename = f'gsm_gate_{kind}_backup_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'

    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_http_methods(['POST'])
def backup_import(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Import zálohy je dostupný jen pro superusera.')

    upload = request.FILES.get('backup_file')
    if not upload:
        messages.error(request, 'Nebyl vybrán žádný soubor k importu.')
        return redirect('backup')

    try:
        raw = upload.read().decode('utf-8')
        json.loads(raw)
    except Exception as exc:
        messages.error(request, f'Soubor není platný JSON export: {exc}')
        return redirect('backup')

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(raw)
            tmp_path = tmp_file.name

        management.call_command('loaddata', tmp_path)
        messages.success(request, 'Import zálohy proběhl úspěšně.')
    except Exception as exc:
        messages.error(request, f'Import zálohy selhal, žádná data se nezměnila: {exc}')
    finally:
        if tmp_path:
            os.remove(tmp_path)

    return redirect('backup')


@login_required
@require_http_methods(['POST'])
def data_reset(request, kind):
    if not request.user.is_superuser:
        raise PermissionDenied('Reset dat je dostupný jen pro superusera.')

    if request.POST.get('confirm', '').strip().upper() != reset_service.CONFIRM_PHRASE:
        messages.error(request, f'Pro potvrzení je nutné napsat přesně „{reset_service.CONFIRM_PHRASE}“. Nic nebylo smazáno.')
        return redirect('backup')

    if kind == 'all':
        summary = reset_service.reset_all(request.user)
        detail = ', '.join(f'{label}: {count}' for label, count in summary.items())
        messages.success(request, f'Kompletní reset brány proběhl. Smazáno – {detail}. Chráněná systémová pravidla a bezpečnostní pravidlo zůstala (jen se resetovaly limity).')
    elif kind in reset_service.RESET_ACTIONS:
        label, func = reset_service.RESET_ACTIONS[kind]
        count = func(request.user)
        messages.success(request, f'{label}: smazáno {count} záznamů.')
    else:
        raise Http404('Neznámý typ resetu.')

    return redirect('backup')


# Sebediagnostika - jen pro superusera, viz services/selftest.py.

@login_required
def self_test_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Sebediagnostika je dostupná jen pro superusera.')

    latest_run = SelfTestRun.objects.filter(owner=request.user).first()
    history = SelfTestRun.objects.filter(owner=request.user)[1:20]

    context = {
        'latest_run': latest_run,
        'grouped_results': selftest_service.group_results(latest_run.results) if latest_run else None,
        'history': history,
    }
    return render(request, 'dashboard/self_test.html', context)


@login_required
def self_test_detail_view(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied('Sebediagnostika je dostupná jen pro superusera.')

    run = get_object_or_404(SelfTestRun, pk=pk, owner=request.user)
    context = {
        'run': run,
        'grouped_results': selftest_service.group_results(run.results),
    }
    return render(request, 'dashboard/self_test_detail.html', context)


@login_required
@require_http_methods(['POST'])
def self_test_run_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Sebediagnostika je dostupná jen pro superusera.')

    overall, results = selftest_service.run_self_test(request.user)
    counts = selftest_service.summarize_counts(results)
    SelfTestRun.objects.create(
        owner=request.user,
        overall_status=overall,
        results=results,
        ok_count=counts['OK'],
        warn_count=counts['WARN'],
        error_count=counts['ERROR'],
    )

    if overall == 'OK':
        messages.success(request, f'Sebediagnostika proběhla bez problémů ({counts["OK"]} kontrol OK).')
    elif overall == 'WARN':
        messages.warning(request, f'Sebediagnostika našla {counts["WARN"]} varování - viz výsledky níže.')
    else:
        messages.error(request, f'Sebediagnostika našla {counts["ERROR"]} chyb(u) - viz výsledky níže.')

    return redirect('self_test')


@login_required
@permission_required('dashboard.view_outgoingaction', raise_exception=True)
def telemetry_view(request):
    user = request.user

    daily_labels, daily_values = telemetry_service.daily_sms_series(user)
    rule_labels, rule_values = telemetry_service.sms_by_rule(user)
    target_labels, target_values = telemetry_service.sms_by_target_number(user)
    source_labels, source_values = telemetry_service.events_by_source_number(user)
    group_labels, group_values = telemetry_service.sms_by_group(user)

    context = {
        'summary': telemetry_service.summary_counts(user),
        'daily_chart': {'labels': daily_labels, 'values': daily_values},
        'rule_chart': {'labels': rule_labels, 'values': rule_values},
        'target_chart': {'labels': target_labels, 'values': target_values},
        'source_chart': {'labels': source_labels, 'values': source_values},
        'group_chart': {'labels': group_labels, 'values': group_values},
    }
    return render(request, 'dashboard/telemetry.html', context)


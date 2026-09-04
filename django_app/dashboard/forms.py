# Formulář pro přidání/úpravu telefonního čísla
from django import forms
from django.db.models import Q
from .models import BlockedNumber, DeviceObject, PhoneNumber, Group, GatewaySettings, AutomationRule  # ← správný model


class BlockedNumberForm(forms.ModelForm):
    class Meta:
        model = BlockedNumber
        fields = ['number', 'reason']

class PhoneNumberForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber
        fields = ['number', 'description', 'active', 'groups']
        widgets = {
            'groups': forms.CheckboxSelectMultiple(),  # pouze widget
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None and user.is_authenticated:
            self.fields['groups'].queryset = Group.objects.filter(users=user)
        else:
            self.fields['groups'].queryset = Group.objects.none()

# Formulář pro Group
class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description']


class BulkNumberGroupAssignForm(forms.Form):
    OPERATION_CHOICES = [
        ('ADD_GROUPS', 'Přidat čísla do vybraných skupin'),
        ('REMOVE_GROUPS', 'Odebrat čísla z vybraných skupin'),
        ('REPLACE_GROUPS', 'Nahradit skupiny u čísel vybranými skupinami'),
        ('SET_ACTIVE', 'Nastavit čísla jako aktivní'),
        ('SET_INACTIVE', 'Nastavit čísla jako neaktivní'),
    ]

    operation = forms.ChoiceField(
        label='Typ hromadné úpravy',
        choices=OPERATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='ADD_GROUPS',
    )

    numbers_raw = forms.CharField(
        label='Telefonní čísla',
        required=False,
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': '+420777111222\n+420777111333\n00420777111444',
            }
        ),
        help_text='Zadejte více čísel, jedno na řádek (nebo oddělené čárkou/středníkem).',
    )
    csv_file = forms.FileField(
        label='CSV soubor s čísly',
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        help_text='Volitelné: nahrajte .csv soubor (UTF-8), čísla mohou být v libovolném sloupci.',
    )
    existing_numbers = forms.ModelMultipleChoiceField(
        queryset=PhoneNumber.objects.none(),
        label='Existující čísla',
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Volitelné: odklikněte čísla ze stávající databáze.',
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        label='Cílové skupiny',
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Vyberte skupiny, které se použijí pro skupinové operace.',
    )
    create_missing = forms.BooleanField(
        label='U operace „Přidat do skupin“ vytvořit chybějící čísla automaticky',
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None and user.is_authenticated:
            self.fields['groups'].queryset = Group.objects.filter(users=user)
            self.fields['existing_numbers'].queryset = PhoneNumber.objects.filter(users=user).order_by('number')

    @staticmethod
    def normalize_phone(raw_value):
        value = (raw_value or '').strip()
        value = ''.join(ch for ch in value if ch.isdigit() or ch == '+')

        if value.startswith('00'):
            value = '+' + value[2:]

        if not value:
            return ''

        if value.count('+') > 1 or ('+' in value[1:]):
            return ''

        if not any(ch.isdigit() for ch in value):
            return ''

        return value

    @staticmethod
    def parse_text_candidates(raw_input):
        import re

        return [item.strip() for item in re.split(r'[\n,;]+', raw_input or '') if item.strip()]

    @staticmethod
    def parse_csv_candidates(csv_file):
        import csv
        import io

        if not csv_file:
            return []

        file_name = (csv_file.name or '').lower()
        if file_name and not file_name.endswith('.csv'):
            raise forms.ValidationError('Nahraný soubor musí mít příponu .csv.')

        try:
            content = csv_file.read().decode('utf-8-sig')
        except Exception:
            raise forms.ValidationError('CSV soubor musí být v kódování UTF-8.')
        finally:
            try:
                csv_file.seek(0)
            except Exception:
                pass

        candidates = []
        reader = csv.reader(io.StringIO(content))
        for row in reader:
            for cell in row:
                cell_value = (cell or '').strip()
                if cell_value:
                    candidates.append(cell_value)

        return candidates

    def validate_candidates(self, candidates, source_label, strict=True):
        normalized_numbers = []
        invalid_values = []

        for candidate in candidates:
            normalized = self.normalize_phone(candidate)
            if not normalized:
                if strict:
                    invalid_values.append(candidate)
                continue
            if normalized not in normalized_numbers:
                normalized_numbers.append(normalized)

        if invalid_values:
            bad_preview = ', '.join(invalid_values[:5])
            raise forms.ValidationError(f'Neplatný formát čísla ({source_label}): {bad_preview}')

        return normalized_numbers

    def clean_numbers_raw(self):
        raw_input = self.cleaned_data.get('numbers_raw', '')
        candidates = self.parse_text_candidates(raw_input)
        self.cleaned_data['parsed_numbers_text'] = self.validate_candidates(candidates, 'textové pole', strict=True)
        return raw_input

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        candidates = self.parse_csv_candidates(csv_file)
        self.cleaned_data['parsed_numbers_csv'] = self.validate_candidates(candidates, 'CSV', strict=False)
        return csv_file

    def clean(self):
        cleaned = super().clean()

        operation = cleaned.get('operation')
        groups = cleaned.get('groups')
        existing_numbers = cleaned.get('existing_numbers')
        parsed_text = cleaned.get('parsed_numbers_text', [])
        parsed_csv = cleaned.get('parsed_numbers_csv', [])
        parsed_existing = [self.normalize_phone(number.number) for number in (existing_numbers or []) if number.number]

        parsed_numbers = []
        for phone in [*parsed_text, *parsed_csv, *parsed_existing]:
            if phone not in parsed_numbers:
                parsed_numbers.append(phone)

        if not parsed_numbers:
            raise forms.ValidationError('Vyberte existující čísla, zadejte čísla ručně nebo nahrajte CSV soubor.')

        if operation in ('ADD_GROUPS', 'REMOVE_GROUPS', 'REPLACE_GROUPS') and not groups:
            self.add_error('groups', 'Pro tuto operaci je nutné vybrat alespoň jednu skupinu.')

        cleaned['parsed_numbers'] = parsed_numbers
        return cleaned


class GatewaySettingsForm(forms.ModelForm):
    class Meta:
        model = GatewaySettings
        fields = [
            'pin_code',
            'delivery_reports',
            'allow_incoming_sms',
            'webhook_url',
        ]
        labels = {
            'pin_code': 'PIN SIM (volitelné)',
            'delivery_reports': 'Vyžadovat doručenky',
            'allow_incoming_sms': 'Povolit příchozí SMS',
            'webhook_url': 'Webhook URL pro Teams (volitelné)',
        }
        widgets = {
            'pin_code': forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
            'webhook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.local/webhook'}),
        }


class AutomationRuleForm(forms.ModelForm):
    source_number_choice = forms.ChoiceField(
        required=False,
        choices=(),
        label='Zdrojové číslo',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    notification_email_choices = forms.MultipleChoiceField(
        required=False,
        choices=(),
        label='E-mailové kontakty z cílových čísel',
        widget=forms.MultipleHiddenInput,
    )

    class Meta:
        model = AutomationRule
        fields = [
            'name',
            'description',
            'active',
            'priority',
            'event_type',
            'match_type',
            'source_number',
            'source_groups',
            'source_objects',
            'use_message_flag',
            'message_flag',
            'action',
            'target_numbers',
            'target_groups',
            'forward_to_number',
            'notify_via_sms',
            'notify_via_email',
            'notify_via_teams',
            'notification_emails',
            'include_original_message',
            'custom_message',
            'notify_first_contact',
            'first_contact_timing',
            'first_contact_message',
            'stop_processing',
        ]
        labels = {
            'name': 'Název pravidla',
            'description': 'Popis',
            'active': 'Aktivní pravidlo',
            'priority': 'Priorita (nižší číslo = dříve)',
            'event_type': 'Typ příchozí události',
            'match_type': 'Typ podmínky',
            'source_number': 'Zdrojové číslo',
            'source_groups': 'Zdrojové skupiny',
            'source_objects': 'Zdrojové objekty',
            'use_message_flag': 'Filtrovat podle příznaku v SMS',
            'message_flag': 'Příznak v SMS',
            'action': 'Reakce',
            'target_numbers': 'Cílová čísla',
            'target_groups': 'Cílové skupiny',
            'forward_to_number': 'Předat na číslo',
            'notify_via_sms': 'Notifikovat přes SMS',
            'notify_via_email': 'Notifikovat přes e-mail',
            'notify_via_teams': 'Notifikovat do Teams',
            'notification_emails': 'Další e-maily pro notifikaci',
            'include_original_message': 'Přiložit původní obsah SMS',
            'custom_message': 'Vlastní text reakce',
            'notify_first_contact': 'Odeslat informační SMS při prvním kontaktu čísla',
            'first_contact_timing': 'Kdy odeslat informační SMS',
            'first_contact_message': 'Text informační SMS',
            'stop_processing': 'Zastavit vyhodnocení dalších pravidel',
        }
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'match_type': forms.Select(attrs={'class': 'form-select'}),
            'source_number': forms.HiddenInput(),
            'source_groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'source_objects': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'message_flag': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ALARM_HIGH'}),
            'action': forms.Select(attrs={'class': 'form-select'}),
            'target_numbers': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'target_groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'forward_to_number': forms.HiddenInput(),
            'notification_emails': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'napr. ops@firma.cz; support@firma.cz'}),
            'custom_message': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Volitelné vlastní znění reakce'}),
            'first_contact_timing': forms.Select(attrs={'class': 'form-select'}),
            'first_contact_message': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Např. Byl jsi zařazen do automatizace X, důvod: ...'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.fields['name'].widget.attrs.update({'class': 'form-control'})

        self.notification_email_candidates = []

        if user is not None and user.is_authenticated:
            user_groups = Group.objects.filter(users=user)
            user_numbers = PhoneNumber.objects.filter(users=user, active=True).order_by('number')
            user_objects = DeviceObject.objects.filter(
                Q(owner=user) | Q(users=user), active=True,
            ).distinct().order_by('name')
            self.fields['source_groups'].queryset = user_groups
            self.fields['target_groups'].queryset = user_groups
            self.fields['target_numbers'].queryset = user_numbers
            self.fields['source_objects'].queryset = user_objects

            source_number_choices = [('', '— Vyberte zdrojové číslo —')]
            for number in user_numbers:
                label = number.number
                if number.description:
                    label = f'{label} — {number.description}'
                source_number_choices.append((number.number, label))
            self.fields['source_number_choice'].choices = source_number_choices

            email_map = {}
            for number in user_numbers:
                email = (number.contact_email or '').strip().lower()
                if not email:
                    continue

                entry = email_map.setdefault(
                    email,
                    {
                        'email': email,
                        'label': email,
                        'number_ids': [],
                        'numbers': [],
                    },
                )
                entry['number_ids'].append(number.pk)
                entry['numbers'].append(number.number)

            candidates = []
            for email, entry in sorted(email_map.items(), key=lambda item: item[0]):
                numbers_preview = ', '.join(entry['numbers'][:3])
                if len(entry['numbers']) > 3:
                    numbers_preview = f'{numbers_preview} ...'
                entry['label'] = f'{email} ({numbers_preview})' if numbers_preview else email
                candidates.append(entry)

            self.notification_email_candidates = candidates
            self.fields['notification_email_choices'].choices = [
                (item['email'], item['label']) for item in candidates
            ]
        else:
            self.fields['source_groups'].queryset = Group.objects.none()
            self.fields['target_groups'].queryset = Group.objects.none()
            self.fields['target_numbers'].queryset = PhoneNumber.objects.none()
            self.fields['source_objects'].queryset = DeviceObject.objects.none()
            self.fields['source_number_choice'].choices = [('', '— Vyberte zdrojové číslo —')]

        if self.instance.pk and self.instance.source_number and not self.is_bound:
            self.initial['source_number_choice'] = self.instance.source_number

        if self.instance.pk and self.instance.notification_emails and not self.is_bound:
            existing_emails = [
                part.strip().lower()
                for part in self.instance.notification_emails.replace(';', ',').split(',')
                if part.strip()
            ]
            selectable = {item['email'] for item in self.notification_email_candidates}
            self.initial['notification_email_choices'] = [email for email in existing_emails if email in selectable]

        if self.instance.pk and self.instance.source_group_id and not self.initial.get('source_groups'):
            self.initial['source_groups'] = [self.instance.source_group_id]

    def clean(self):
        cleaned = super().clean()
        match_type = cleaned.get('match_type')
        action = cleaned.get('action')
        source_number = cleaned.get('source_number')
        source_groups = cleaned.get('source_groups')
        source_number_choice = (cleaned.get('source_number_choice') or '').strip()
        source_objects = cleaned.get('source_objects')
        target_numbers = cleaned.get('target_numbers')
        target_groups = cleaned.get('target_groups')
        forward_to_number = (cleaned.get('forward_to_number') or '').strip()
        event_type = cleaned.get('event_type')
        use_message_flag = cleaned.get('use_message_flag')
        message_flag = (cleaned.get('message_flag') or '').strip()
        notify_via_sms = cleaned.get('notify_via_sms')
        notify_via_email = cleaned.get('notify_via_email')
        notify_via_teams = cleaned.get('notify_via_teams')
        notification_emails = cleaned.get('notification_emails') or ''
        notification_email_choices = cleaned.get('notification_email_choices') or []

        # For pure API events the JS forces match_type='ANY'; honour that server-side too.
        api_only = event_type == 'API'
        if api_only and match_type != 'ANY':
            match_type = 'ANY'
            cleaned['match_type'] = 'ANY'

        if match_type == 'EXACT' and not source_number and source_number_choice:
            source_number = source_number_choice
            cleaned['source_number'] = source_number

        if match_type == 'EXACT' and not source_number:
            # Add the error on the visible helper field so the wizard navigates to the right step.
            self.add_error('source_number_choice', 'Pro tento typ match je zdrojové číslo povinné.')

        if match_type == 'GROUP' and not source_groups:
            self.add_error('source_groups', 'Pro tento typ match je nutné vybrat alespoň jednu zdrojovou skupinu.')

        if event_type in ('API', 'SMS_API') and not source_objects:
            self.add_error('source_objects', 'Pro zvolený typ události je nutné vybrat alespoň jeden zdrojový objekt.')

        if use_message_flag and not message_flag:
            self.add_error('message_flag', 'Pokud je zapnutý filtr podle příznaku, vyplňte příznak v SMS.')

        if action in ('NOTIFY_NUM', 'NOTIFY_GRP') and not (notify_via_sms or notify_via_email or notify_via_teams):
            self.add_error('notify_via_sms', 'Vyberte alespoň jeden notifikační kanál.')

        if action == 'NOTIFY_NUM' and not target_numbers:
            self.add_error('target_numbers', 'Vyber cílová čísla pro notifikaci.')

        if action == 'NOTIFY_GRP' and not target_groups:
            self.add_error('target_groups', 'Vyber cílové skupiny pro notifikaci.')

        if action == 'FORWARD':
            if not forward_to_number and target_numbers:
                first_target = target_numbers.first()
                forward_to_number = first_target.number if first_target else ''
                cleaned['forward_to_number'] = forward_to_number
            if not forward_to_number:
                self.add_error('target_numbers', 'Pro akci „Předat na číslo“ vyberte alespoň jedno cílové číslo.')

        typed_emails = [
            part.strip().lower()
            for part in notification_emails.replace(';', ',').split(',')
            if part.strip()
        ]
        merged_emails = []
        for email in [*notification_email_choices, *typed_emails]:
            normalized = (email or '').strip().lower()
            if normalized and normalized not in merged_emails:
                merged_emails.append(normalized)

        if notify_via_email:
            cleaned['notification_emails'] = '; '.join(merged_emails)
        else:
            cleaned['notification_emails'] = ''

        if match_type == 'EXACT':
            cleaned['source_groups'] = Group.objects.none()
            cleaned['source_group'] = None
        elif match_type == 'GROUP':
            cleaned['source_number'] = ''
            cleaned['source_group'] = None
        elif match_type == 'ANY':
            cleaned['source_number'] = ''
            cleaned['source_groups'] = Group.objects.none()
            cleaned['source_group'] = None

        if action == 'FORWARD':
            cleaned['target_numbers'] = PhoneNumber.objects.none()
            cleaned['target_groups'] = Group.objects.none()
        elif action == 'NOTIFY_NUM':
            cleaned['target_groups'] = Group.objects.none()
            cleaned['forward_to_number'] = ''
        elif action == 'NOTIFY_GRP':
            cleaned['target_numbers'] = PhoneNumber.objects.none()
            cleaned['forward_to_number'] = ''
        else:
            cleaned['forward_to_number'] = ''

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        match_type = self.cleaned_data.get('match_type')
        source_groups = self.cleaned_data.get('source_groups')

        if match_type == 'GROUP' and source_groups:
            instance.source_group = source_groups.first()
        else:
            instance.source_group = None

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class IncomingEventSimulationForm(forms.Form):
    EVENT_CHOICES = [
        ('SMS', 'Příchozí SMS'),
        ('CALL', 'Příchozí volání'),
    ]

    event_type = forms.ChoiceField(choices=EVENT_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    source_number = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+420777000111'}))
    message_body = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event_type'].label = 'Typ události'
        self.fields['source_number'].label = 'Příchozí číslo'
        self.fields['message_body'].label = 'Obsah zprávy (pro SMS)'
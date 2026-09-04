# tabulky pro ukládání čísel a jejich vlastností

import secrets

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


# tabulka pro skupiny čísel
class Group(models.Model):

    # název a popis skupiny
    name = models.CharField('Název', max_length=100)
    # volitelný popis skupiny
    description = models.CharField('Popis', max_length=255, blank=True)

    # vlastník skupiny (ten, kdo skupinu vytvořil)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_groups',
        verbose_name='Vlastník',
    )


    # skupina může mít více uživatelů (sdílení)
    users = models.ManyToManyField(User, related_name='shared', blank=True, verbose_name='Uživatelé')
    # zobrazení názvu skupiny
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Skupina'
        verbose_name_plural = 'Skupiny'


# tabulka pro telefonní čísla
class PhoneNumber(models.Model):

    # vlastník čísla (ten, kdo číslo vytvořil)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_numbers', verbose_name='Vlastník')
    # číslo může mít více uživatelů (sdílení)
    users = models.ManyToManyField(User, related_name='shared_numbers', blank=True, verbose_name='Uživatelé se sdílením')

    # samotné číslo a jeho popis
    number = models.CharField('Telefonní číslo', max_length=20)

    # volitelný popis čísla
    description = models.CharField('Popis', max_length=100, blank=True)

    # volitelný e-mail kontaktu k číslu
    contact_email = models.EmailField('Kontaktní e-mail', blank=True)

    # zda je číslo aktivní
    active = models.BooleanField('Aktivní', default=True)

    # číslo může být v jedné nebo více skupinách
    groups = models.ManyToManyField(Group, related_name='phone_numbers', blank=True, verbose_name='Skupiny')


    # zobrazení čísla jako textu
    def __str__(self):
        return self.number

    class Meta:
        verbose_name = 'Telefonní číslo'
        verbose_name_plural = 'Telefonní čísla'


class UserGroupVisibilityOverride(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_visibility_overrides', verbose_name='Uživatel')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='visibility_overrides', verbose_name='Skupina')
    hidden_numbers = models.ManyToManyField(PhoneNumber, blank=True, related_name='hidden_in_visibility_overrides', verbose_name='Skrytá čísla')

    class Meta:
        verbose_name = 'Výjimka viditelnosti skupiny'
        verbose_name_plural = 'Výjimky viditelnosti skupin'
        constraints = [
            models.UniqueConstraint(fields=['user', 'group'], name='unique_user_group_visibility_override')
        ]

    def __str__(self):
        return f"{self.user.username} / {self.group.name}"

    def clean(self):
        super().clean()
        if not self.pk:
            return

        group_numbers_ids = set(self.group.phone_numbers.values_list('id', flat=True))
        hidden_ids = set(self.hidden_numbers.values_list('id', flat=True))
        invalid_ids = hidden_ids - group_numbers_ids
        if invalid_ids:
            raise ValidationError('Skrytá čísla musí patřit do vybrané skupiny.')
    

# tabulka pro pravidla (pro budoucí použití)
class Rule(models.Model):
    # název pravidla
    name = models.CharField('Název', max_length=100)
    # popis pravidla
    description = models.TextField('Popis', blank=True)
    # zda je pravidlo aktivní
    active = models.BooleanField('Aktivní', default=True)


    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Pravidlo'
        verbose_name_plural = 'Pravidla'


class DeviceObject(models.Model):
    OBJECT_TYPE_CHOICES = [
        ('FREEZER', 'Mrazák'),
        ('ALARM', 'Alarm'),
        ('SENSOR', 'Senzor'),
        ('GATEWAY', 'Brána'),
        ('OTHER', 'Jiný objekt'),
    ]

    STATUS_CHOICES = [
        ('OK', 'OK'),
        ('WARN', 'Varování'),
        ('ALERT', 'Poplach'),
        ('OFFLINE', 'Offline'),
    ]

    ICON_CHOICES = [
        ('snow', 'Mrazák'),
        ('bell', 'Alarm'),
        ('thermometer-half', 'Teplota'),
        ('shield-exclamation', 'Bezpečnost'),
        ('wifi', 'Síť'),
        ('hdd-network', 'Zařízení'),
        ('cpu', 'Řídicí jednotka'),
        ('lightning-charge', 'Energie'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_objects', verbose_name='Vlastník')
    name = models.CharField('Název objektu', max_length=120)
    object_label = models.CharField('Vlastní popisek objektu', max_length=120, blank=True)
    object_type = models.CharField('Typ objektu', max_length=20, choices=OBJECT_TYPE_CHOICES, default='OTHER')
    icon = models.CharField('Ikona', max_length=40, choices=ICON_CHOICES, default='hdd-network')
    active = models.BooleanField('Aktivní', default=True)
    status_flag = models.CharField('Příznak stavu', max_length=10, choices=STATUS_CHOICES, default='OK')
    status_label = models.CharField('Vlastní popisek stavu', max_length=120, blank=True)
    description = models.CharField('Popis', max_length=255, blank=True)
    specification = models.TextField('Specifikace', blank=True)
    created_at = models.DateTimeField('Vytvořeno', auto_now_add=True)
    updated_at = models.DateTimeField('Upraveno', auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        verbose_name = 'Objekt zařízení'
        verbose_name_plural = 'Objekty zařízení'

    def __str__(self):
        return f'{self.name} ({self.owner.username})'


class DeviceObjectApiCredential(models.Model):
    device_object = models.OneToOneField(DeviceObject, on_delete=models.CASCADE, related_name='api_credential', verbose_name='Objekt zařízení')
    token = models.CharField('API token', max_length=128, unique=True)
    active = models.BooleanField('Aktivní', default=True)
    created_at = models.DateTimeField('Vytvořeno', auto_now_add=True)
    updated_at = models.DateTimeField('Upraveno', auto_now=True)
    last_used_at = models.DateTimeField('Naposledy použito', null=True, blank=True)

    class Meta:
        verbose_name = 'API klíč objektu'
        verbose_name_plural = 'API klíče objektů'

    def __str__(self):
        return f'API klíč: {self.device_object.name}'

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)


class GatewaySettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gateway_settings', verbose_name='Uživatel')
    pin_code = models.CharField(
        'PIN SIM',
        max_length=16,
        blank=True,
        help_text='Vyplň, jen pokud SIM karta vyžaduje PIN. Worker ho použije k odemčení modemu.',
    )
    delivery_reports = models.BooleanField(
        'Vyžadovat doručenky',
        default=True,
        help_text='Při odeslání SMS požádá síť o potvrzení doručení příjemci.',
    )
    allow_incoming_sms = models.BooleanField('Povolit příchozí SMS', default=True)
    webhook_url = models.URLField('Webhook URL (Teams)', blank=True)
    updated_at = models.DateTimeField('Naposledy změněno', auto_now=True)

    last_signal_quality = models.PositiveIntegerField('Poslední síla signálu (%)', null=True, blank=True)
    last_signal_checked_at = models.DateTimeField('Signál naposledy zjištěn', null=True, blank=True)

    def __str__(self):
        return f"Nastavení brány: {self.user.username}"

    @property
    def signal_label(self):
        if self.last_signal_quality is None:
            return 'Neznámý'
        if self.last_signal_quality >= 80:
            return 'Výborný'
        if self.last_signal_quality >= 60:
            return 'Dobrý'
        if self.last_signal_quality >= 35:
            return 'Slabý'
        return 'Velmi slabý'

    @property
    def signal_dbm(self):
        # ModemManager vrací sílu signálu jako procento bez jednoznačného
        # převodu na dBm, na rozdíl od starého CSQ (0-31) u SIM7000E.
        return None

    class Meta:
        verbose_name = 'Nastavení brány'
        verbose_name_plural = 'Nastavení brány'


class AutomationRule(models.Model):
    EVENT_TYPE_CHOICES = [
        ('SMS', 'Příchozí SMS'),
        ('API', 'Příchozí API událost'),
        ('SMS_API', 'SMS i API událost'),
        ('ANY', 'SMS i API událost'),
        ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
    ]

    MATCH_TYPE_CHOICES = [
        ('ANY', 'Jakékoliv číslo'),
        ('EXACT', 'Konkrétní číslo'),
        ('GROUP', 'Číslo ze skupiny'),
    ]

    ACTION_CHOICES = [
        ('IGNORE', 'Ignorovat'),
        ('NOTIFY_NUM', 'Poslat informaci na cílová čísla'),
        ('NOTIFY_GRP', 'Poslat informaci na cílové skupiny'),
        ('FORWARD', 'Předat na číslo'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='automation_rules', verbose_name='Vlastník')
    users = models.ManyToManyField(User, blank=True, related_name='shared_automation_rules', verbose_name='Přiřazení uživatelé')
    name = models.CharField('Název pravidla', max_length=120)
    description = models.CharField('Popis', max_length=255, blank=True)
    active = models.BooleanField('Aktivní', default=True)
    priority = models.PositiveIntegerField('Priorita', default=100)
    is_protected = models.BooleanField(
        'Chráněné systémové pravidlo',
        default=False,
        help_text='Nejde smazat ani upravit v appce – jen zapnout/vypnout a nastavit přes Django Admin.',
    )

    event_type = models.CharField('Typ události', max_length=20, choices=EVENT_TYPE_CHOICES, default='ANY')
    match_type = models.CharField('Typ podmínky', max_length=10, choices=MATCH_TYPE_CHOICES, default='ANY')
    source_number = models.CharField('Zdrojové číslo', max_length=30, blank=True)
    source_group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_automation_rules',
        verbose_name='Zdrojová skupina',
    )
    source_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name='source_automation_rules_multi',
        verbose_name='Zdrojové skupiny',
    )
    source_objects = models.ManyToManyField(
        DeviceObject,
        blank=True,
        related_name='source_automation_rules',
        verbose_name='Zdrojové objekty',
    )

    action = models.CharField('Reakce', max_length=10, choices=ACTION_CHOICES, default='IGNORE')
    target_numbers = models.ManyToManyField(PhoneNumber, blank=True, related_name='targeted_by_rules', verbose_name='Cílová čísla')
    target_groups = models.ManyToManyField(Group, blank=True, related_name='targeted_by_rules', verbose_name='Cílové skupiny')
    use_message_flag = models.BooleanField('Filtrovat podle příznaku v SMS', default=False)
    message_flag = models.CharField('Příznak v SMS', max_length=60, blank=True)
    forward_to_number = models.CharField('Předat na číslo', max_length=30, blank=True)
    notify_via_sms = models.BooleanField('Notifikovat přes SMS', default=True)
    notify_via_email = models.BooleanField('Notifikovat přes e-mail', default=False)
    notify_via_teams = models.BooleanField('Notifikovat do Teams', default=False)
    notification_emails = models.TextField('Další e-maily pro notifikaci', blank=True)
    include_original_message = models.BooleanField('Přiložit původní zprávu', default=True)
    custom_message = models.CharField('Vlastní text', max_length=320, blank=True)
    stop_processing = models.BooleanField('Zastavit další vyhodnocení', default=True)

    notify_first_contact = models.BooleanField(
        'Odeslat informační SMS při prvním kontaktu čísla',
        default=False,
        help_text='Když tohle pravidlo osloví dané cílové číslo poprvé, pošle navíc jednorázovou informační SMS (text níže).',
    )
    first_contact_message = models.CharField(
        'Text informační SMS',
        max_length=320,
        blank=True,
        help_text='Např. "Bylo jsi zařazen do automatizace X, důvod: ...". Odešle se jen jednou na dané číslo, při prvním kontaktu tímto pravidlem.',
    )

    created_at = models.DateTimeField('Vytvořeno', auto_now_add=True)
    updated_at = models.DateTimeField('Upraveno', auto_now=True)

    class Meta:
        ordering = ['priority', 'id']
        verbose_name = 'Automatizační pravidlo'
        verbose_name_plural = 'Automatizační pravidla'

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def clean(self):
        super().clean()
        event_type_includes_api = self.event_type in ('API', 'SMS_API', 'CALL_API', 'ALL')
        if not (self.name or '').strip():
            raise ValidationError('Název pravidla je povinný.')
        if not (self.description or '').strip():
            raise ValidationError('Popis pravidla je povinný.')
        if self.match_type == 'EXACT' and not self.source_number:
            raise ValidationError('Pro match "Konkrétní číslo" je nutné vyplnit zdrojové číslo.')
        if self.match_type == 'GROUP':
            has_source_group = bool(self.source_group)
            has_source_groups = False
            if self.pk:
                has_source_groups = self.source_groups.exists()

            if not has_source_group and not has_source_groups and not self._state.adding:
                raise ValidationError('Pro match "Číslo ze skupiny" je nutné zvolit zdrojovou skupinu.')
        if event_type_includes_api and self.pk and not self.source_objects.exists():
            raise ValidationError('Pro API události je nutné zvolit alespoň jeden zdrojový objekt.')
        if self.action == 'FORWARD' and not self.forward_to_number:
            raise ValidationError('Pro akci "Předat na číslo" je nutné vyplnit cílové číslo.')
        if self.use_message_flag and not self.message_flag.strip():
            raise ValidationError('Pokud je zapnutý filtr podle příznaku, vyplňte příznak v SMS.')


class SecurityRule(models.Model):
    """Pevně dané bezpečnostní pravidlo proti zahlcení SMS/API událostmi.

    Jde o singleton na uživatele – vytváří se automaticky (get_or_create),
    dá se jen upravit a zapnout/vypnout, nedá se smazat (žádné delete view).
    """

    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security_rule', verbose_name='Vlastník')
    active = models.BooleanField('Aktivní', default=True)
    rate_limit_window_minutes = models.PositiveIntegerField(
        'Časové okno (min)', default=10,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )
    rate_limit_max_events = models.PositiveIntegerField(
        'Max. událostí v okně', default=20,
        validators=[MinValueValidator(1)],
    )
    auto_block_cooldown_minutes = models.PositiveIntegerField(
        'Doba automatické blokace (min)', default=30,
        validators=[MinValueValidator(1), MaxValueValidator(10080)],
    )
    updated_at = models.DateTimeField('Naposledy změněno', auto_now=True)

    class Meta:
        verbose_name = 'Bezpečnostní pravidlo'
        verbose_name_plural = 'Bezpečnostní pravidla'

    def __str__(self):
        return f"Bezpečnostní pravidlo: {self.owner.username}"


class BlockedNumber(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_numbers', verbose_name='Vlastník')
    number = models.CharField('Telefonní číslo', max_length=30)
    reason = models.CharField('Důvod', max_length=255, blank=True)
    created_at = models.DateTimeField('Vytvořeno', auto_now_add=True)
    expires_at = models.DateTimeField('Platí do', null=True, blank=True, help_text='Prázdné = trvalá blokace.')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Blokované číslo'
        verbose_name_plural = 'Blokovaná čísla'
        unique_together = [('owner', 'number')]

    def __str__(self):
        return f"{self.number} ({self.owner.username})"

    @property
    def is_active(self):
        return self.expires_at is None or self.expires_at > timezone.now()


class IncomingEventLog(models.Model):
    EVENT_TYPE_CHOICES = [
        ('SMS', 'Příchozí SMS'),
        ('API', 'Příchozí API událost'),
        ('SECURITY', 'Bezpečnostní událost (zablokování čísla)'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incoming_event_logs', verbose_name='Vlastník')
    event_type = models.CharField('Typ události', max_length=20, choices=EVENT_TYPE_CHOICES)
    source_number = models.CharField('Zdrojové číslo', max_length=30)
    message_body = models.TextField('Obsah zprávy', blank=True)
    processed = models.BooleanField('Zpracováno', default=False)
    result_summary = models.TextField('Výsledek zpracování', blank=True)
    created_at = models.DateTimeField('Čas přijetí', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Záznam příchozí události'
        verbose_name_plural = 'Záznamy příchozích událostí'

    def __str__(self):
        return f"{self.get_event_type_display()} from {self.source_number}"


class OutgoingAction(models.Model):
    ACTION_TYPE_CHOICES = [
        ('NOTIFY_SMS', 'Notifikační SMS'),
        ('NOTIFY_EMAIL', 'Notifikační e-mail'),
        ('NOTIFY_TEAMS', 'Notifikace do Teams'),
        ('FORWARD_INFO', 'Předání na číslo'),
        ('DEVICE_PULL', 'Vyzvednutí požadavku objektu'),
        ('INFO_SMS', 'Informační SMS (první kontakt)'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Čeká'),
        ('SENT', 'Odesláno'),
        ('FAILED', 'Chyba'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='outgoing_actions', verbose_name='Vlastník')
    event_log = models.ForeignKey(IncomingEventLog, on_delete=models.CASCADE, related_name='actions', verbose_name='Zdrojová událost')
    rule = models.ForeignKey(AutomationRule, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Pravidlo')

    action_type = models.CharField('Typ akce', max_length=20, choices=ACTION_TYPE_CHOICES)
    target_number = models.CharField('Cílové číslo', max_length=30)
    payload_message = models.TextField('Text akce')
    status = models.CharField('Stav', max_length=10, choices=STATUS_CHOICES, default='PENDING')
    processed_at = models.DateTimeField('Zpracováno', null=True, blank=True)
    execution_detail = models.TextField('Detail zpracování', blank=True)
    created_at = models.DateTimeField('Vytvořeno', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Odchozí akce'
        verbose_name_plural = 'Odchozí akce'

    def __str__(self):
        return f"{self.action_type} -> {self.target_number}"

    def clean(self):
        super().clean()

        if self.event_log_id and self.owner_id and self.event_log.owner_id != self.owner_id:
            raise ValidationError('Vlastník akce musí odpovídat vlastníkovi zdrojové události.')

        if self.rule_id and self.owner_id:
            is_rule_owner = self.rule.owner_id == self.owner_id
            is_assigned_user = self.rule.users.filter(id=self.owner_id).exists()
            if not is_rule_owner and not is_assigned_user:
                raise ValidationError('Vlastník akce musí být vlastník navázaného pravidla nebo jeho přiřazený uživatel.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class SelfTestRun(models.Model):
    """Historie spuštění sebediagnostiky (dashboard/services/selftest.py).
    Jen pro superusera - viz views.self_test_view/self_test_run_view."""

    STATUS_CHOICES = [
        ('OK', 'OK'),
        ('WARN', 'Varování'),
        ('ERROR', 'Chyba'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='self_test_runs', verbose_name='Spustil')
    created_at = models.DateTimeField('Spuštěno', auto_now_add=True)
    overall_status = models.CharField('Celkový výsledek', max_length=10, choices=STATUS_CHOICES)
    results = models.JSONField('Výsledky kontrol', default=list)
    ok_count = models.PositiveIntegerField('Počet OK', default=0)
    warn_count = models.PositiveIntegerField('Počet varování', default=0)
    error_count = models.PositiveIntegerField('Počet chyb', default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sebediagnostika'
        verbose_name_plural = 'Sebediagnostiky'

    def __str__(self):
        return f"Sebediagnostika {self.created_at:%d.%m.%Y %H:%M} - {self.get_overall_status_display()}"


class SignalReading(models.Model):
    """Historie síly signálu modemu - zapisuje gsm_worker při každém cyklu
    (viz services/gsm_worker.py), max. jednou za pár minut (throttling v
    _record_signal_reading), aby tabulka nerostla neúměrně rychle. quality=None
    znamená výpadek (modem nebyl v tom cyklu dostupný) - slouží k detekci
    výpadků v Telemetrii, ne jen k zobrazení aktuální hodnoty."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='signal_readings', verbose_name='Vlastník')
    quality = models.PositiveIntegerField(
        'Síla signálu (%)', null=True, blank=True,
        help_text='Prázdné = modem nebyl v tomto cyklu dostupný (výpadek).',
    )
    recorded_at = models.DateTimeField('Zaznamenáno', auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'Záznam síly signálu'
        verbose_name_plural = 'Záznamy síly signálu'

    def __str__(self):
        value = self.quality if self.quality is not None else 'výpadek'
        return f"{self.recorded_at:%d.%m.%Y %H:%M} - {value}"
import logging

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from dashboard.services import ratelimit
from dashboard.services.rules_engine import fire_system_health_event

logger = logging.getLogger(__name__)

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


# Brute-force zámek na přihlášení - viz urls.py (LoginView používá tenhle
# formulář místo výchozího AuthenticationForm). Klíč je IP+username
# dohromady: čistě per-IP by šlo zablokovat sdílenou síť kvůli jednomu
# útočníkovi, čistě per-username by šlo cizí účet zamknout jen znalostí
# jména (bez hesla) odkudkoliv.
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 300


class LockoutAuthenticationForm(AuthenticationForm):
    def clean(self):
        client_ip = self.request.META.get('REMOTE_ADDR', 'unknown') if self.request else 'unknown'
        username = (self.cleaned_data.get('username') or '').strip().lower()
        fail_key = f'login_fail:{client_ip}:{username}'

        if ratelimit.get_failure_count(fail_key) >= LOGIN_MAX_FAILURES:
            raise ValidationError(
                'Příliš mnoho neúspěšných pokusů o přihlášení. Zkus to znovu za pár minut.',
                code='too_many_attempts',
            )

        try:
            cleaned_data = super().clean()
        except ValidationError:
            count = ratelimit.register_failure(fail_key, LOGIN_WINDOW_SECONDS)
            # Jen jednou, přesně v okamžiku, kdy se zámek poprvé spustí -
            # další zablokované pokusy skončí na kontrole výše (bez
            # register_failure), ať to nezaspamuje admina opakovaně.
            if count == LOGIN_MAX_FAILURES:
                try:
                    fire_system_health_event(
                        '#LOGIN_ATTACK',
                        f'Příliš mnoho neúspěšných pokusů o přihlášení (IP: {client_ip}, uživatel: {username or "neznámý"}).',
                        source_number=client_ip,
                    )
                except Exception:
                    logger.exception('Chyba při generování události o útoku na přihlášení')
            raise

        ratelimit.reset_failures(fail_key)
        return cleaned_data
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from dashboard.services import ratelimit

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
            ratelimit.register_failure(fail_key, LOGIN_WINDOW_SECONDS)
            raise

        ratelimit.reset_failures(fail_key)
        return cleaned_data
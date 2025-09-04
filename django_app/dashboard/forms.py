from django import forms
from .models import PhoneNumber  # ← správný model

class PhoneNumberForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber  # ← tady už ne DashboardModel
        fields = ['number', 'description', 'active']  # uprav podle svého modelu
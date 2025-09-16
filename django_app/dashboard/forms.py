# Formulář pro přidání/úpravu telefonního čísla
from django import forms
from .models import PhoneNumber, Group  # ← správný model

class PhoneNumberForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber
        fields = ['number', 'description', 'active', 'groups']
        widgets = {
            'groups': forms.CheckboxSelectMultiple(),  # pouze widget
        }

# Formulář pro Group
class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description']                  
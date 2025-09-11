# logika pro zobrazení dashboardu a správu čísel
# jinja2 šablony jsou v django_app/dashboard/templates/dashboard/

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PhoneNumber
from .forms import PhoneNumberForm


# Zobrazení dashboardu s čísly uživatele
@login_required
def dashboard_view(request):
    numbers = PhoneNumber.objects.filter(users=request.user)
    return render(request, 'dashboard/dashboard.html', {'numbers': numbers})

# Vytvoření nového čísla
def number_create(request):
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
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
        form = PhoneNumberForm()
    return render(request, 'dashboard/number_form.html', {'form': form})

# Úprava existujícího čísla
@login_required
def number_update(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, users=request.user)
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST, instance=number)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = PhoneNumberForm(instance=number)
    return render(request, 'dashboard/number_form.html', {'form': form})

# Smazání čísla
@login_required
def number_delete(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, users=request.user)
    if request.method == 'POST':
        number.delete()
        return redirect('dashboard')
    return render(request, 'dashboard/number_confirm_delete.html', {'number': number})
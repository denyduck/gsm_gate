# logika pro zobrazení dashboardu a správu čísel
# jinja2 šablony jsou v django_app/dashboard/templates/dashboard/

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import PhoneNumber, Group
from .forms import PhoneNumberForm, GroupForm


# Zobrazení dashboardu s čísly uživatele
@login_required
def dashboard_view(request):
    # vyber všechna čísla, kde je uživatel v uživatelích
    numbers = PhoneNumber.objects.filter(users=request.user)
    # vyber všechny skupiny, kde je uživatel vlastníkem nebo je alespon v uživatelích
    groups = Group.objects.filter(users=request.user)
    # předání čísel a skupin do šablony
    
    context = {
        'numbers': numbers,
        'groups': groups,
    }

    return render(request, 'dashboard/dashboard.html', context)


######################################################################################################
#CRUD OPERACE S ČÍSLY
######################################################################################################
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

######################################################################################################
#CRUD OPERACE SE SKUPINAMI
######################################################################################################
# Vytvoření nové skupiny
@login_required
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)

        if form.is_valid():
            group = form.save(commit=False)  # nevytváří hned v DB
            group = form.save()              # uloží skupinu do DB
            # přidat vlastníka do uživatelů
            group.users.add(request.user)
            return redirect('dashboard')
    else:
        form = GroupForm()
    return render(request, 'dashboard/group_form.html', {'form': form})

# Úprava existující skupiny
@login_required
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
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk, users=request.user)
    if request.method == 'POST':
        group.delete()
        return redirect('dashboard')
    return render(request, 'dashboard/group_confirm_delete.html', {'group': group})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PhoneNumber
from .forms import PhoneNumberForm

@login_required
def dashboard_view(request):
    numbers = PhoneNumber.objects.filter(user=request.user)
    return render(request, 'dashboard/dashboard.html', {'numbers': numbers})

@login_required
def number_create(request):
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
        if form.is_valid():
            number = form.save(commit=False)
            number.user = request.user
            number.save()
            return redirect('dashboard')
    else:
        form = PhoneNumberForm()
    return render(request, 'dashboard/number_form.html', {'form': form})

@login_required
def number_update(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PhoneNumberForm(request.POST, instance=number)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = PhoneNumberForm(instance=number)
    return render(request, 'dashboard/number_form.html', {'form': form})

@login_required
def number_delete(request, pk):
    number = get_object_or_404(PhoneNumber, pk=pk, user=request.user)
    if request.method == 'POST':
        number.delete()
        return redirect('dashboard')
    return render(request, 'dashboard/number_confirm_delete.html', {'number': number})
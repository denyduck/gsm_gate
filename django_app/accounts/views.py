from django.shortcuts import render
from .forms import RegisterForm

def register_view(request):
    form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})
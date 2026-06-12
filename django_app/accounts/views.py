from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import RegisterForm

def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            messages.success(
                request,
                "Registrace proběhla úspěšně. Účet čeká na schválení správcem nebo administrátorem.",
            )
            return redirect("login")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})

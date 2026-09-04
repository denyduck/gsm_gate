from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render


def home_view(request):
    return render(request, 'home.html')


def health_check(request):
    """Pro Docker healthcheck (docker-compose.yml) - bez přihlášení, žádné
    citlivé informace, jen ověří, že appka odpovídá a DB je dostupná."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return HttpResponse('OK')

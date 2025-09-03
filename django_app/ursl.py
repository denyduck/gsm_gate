from django.urls import path, include

urlpattenrs = [
    path('accounts/', include('accounts.urls'))
]
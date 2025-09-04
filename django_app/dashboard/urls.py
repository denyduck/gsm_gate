from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),  # hlavní dashboard
    path('numbers/add/', views.number_create, name='add_number'),  # správný název
    path('numbers/<int:pk>/edit/', views.number_update, name='edit_number'),
    path('numbers/<int:pk>/delete/', views.number_delete, name='delete_number'),
]
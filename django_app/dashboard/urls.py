# URL konfigurace pro dashboard aplikaci
# Nyní zahrnují CRUD operace pro PhoneNumber

from django.urls import path
from . import views

# URL vzory pro dashboard aplikaci
urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),                           # hlavní dashboard
    path('numbers/add/', views.number_create, name='add_number'),               # správný název
    path('numbers/<int:pk>/edit/', views.number_update, name='edit_number'),
    path('numbers/<int:pk>/delete/', views.number_delete, name='delete_number'),

    path('groups/add/', views.group_create, name='add_group'),                  # přidání skupiny
    path('groups/<int:pk>/edit/', views.group_update, name='edit_group'),       # úprava skupiny
    path('groups/<int:pk>/delete/', views.group_delete, name='delete_group'),   # smazání skupiny

]
# URL konfigurace pro dashboard aplikaci
# Nyní zahrnují CRUD operace pro PhoneNumber

from django.urls import path
from . import views

# URL vzory pro dashboard aplikaci
urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),                           # hlavní dashboard
    path('gateway/status/', views.gateway_status_view, name='gateway_status'),
    path('gateway/settings/', views.gateway_settings_view, name='gateway_settings'),
    path('rules/', views.rules_list_view, name='rules_list'),
    path('rules/add/', views.rule_create, name='rule_add'),
    path('rules/<int:pk>/', views.rule_detail, name='rule_detail'),
    path('rules/<int:pk>/edit/', views.rule_update, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete, name='rule_delete'),
    path('events/simulate/', views.incoming_simulator_view, name='incoming_simulator'),
    path('events/logs/', views.event_logs_view, name='event_logs'),
    path('events/logs/<int:pk>/', views.event_log_detail_view, name='event_log_detail'),
    path('events/outgoing/', views.outgoing_actions_view, name='outgoing_actions'),
    path('numbers/add/', views.number_create, name='add_number'),               # správný název
    path('numbers/bulk-add/', views.number_bulk_add, name='number_bulk_add'),
    path('numbers/bulk-add/template.csv', views.number_bulk_csv_template, name='number_bulk_csv_template'),
    path('numbers/<int:pk>/', views.number_detail, name='number_detail'),
    path('numbers/<int:pk>/edit/', views.number_update, name='edit_number'),
    path('numbers/<int:pk>/delete/', views.number_delete, name='delete_number'),

    path('groups/add/', views.group_create, name='add_group'),                  # přidání skupiny
    path('groups/<int:pk>/', views.group_detail, name='group_detail'),
    path('groups/<int:pk>/edit/', views.group_update, name='edit_group'),       # úprava skupiny
    path('groups/<int:pk>/delete/', views.group_delete, name='delete_group'),   # smazání skupiny

    path('objects/', views.device_objects_list_view, name='device_objects_list'),
    path('objects/add/', views.device_object_create, name='device_object_add'),
    path('objects/<int:pk>/', views.device_object_detail, name='device_object_detail'),
    path('objects/<int:pk>/edit/', views.device_object_update, name='device_object_edit'),
    path('objects/<int:pk>/delete/', views.device_object_delete, name='device_object_delete'),
    path('objects/<int:pk>/api-key/regenerate/', views.device_object_regenerate_api_key, name='device_object_regenerate_api_key'),
    path('objects/<int:pk>/api-config/export/', views.device_object_export_config, name='device_object_export_config'),

    path('api/device-events/ingest/', views.device_event_ingest_api, name='device_event_ingest_api'),

]
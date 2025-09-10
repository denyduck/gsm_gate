from django.contrib import admin
from dashboard.models import Group, PhoneNumber

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'id')
    search_fields = ('name', 'description')




@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('number', 'description', 'active', 'user')
    list_filter = ('active', 'user')
    search_fields = ('number', 'description', 'user__username')
    filter_horizontal = ('groups', 'users')  # funguje jen pokud pole groups existuje
    raw_id_fields = ('user',)
    ordering = ('number',)
    fieldsets = (
        (None, {
            'fields': ('number', 'description', 'active', 'user', 'groups', 'users')
        }),
    )

# Admin rozhraní pro modely Group a PhoneNumber
# slouží k pohodlné správě přes Django admin a zobrazení důležitých polí

from django.contrib import admin
from dashboard.models import Group, PhoneNumber, Rule

# Funkce pro zobrazení všech uživatelů M2M v jednom sloupci
def users_list(obj):
    return ", ".join([u.username for u in obj.users.all()])
users_list.short_description = "Uživatelé"


##################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Phone Numbers"
##################################################################################################
# Registrace modelu PhoneNumber do admin rozhraní django a další přdané funkce
@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('number', 'description', 'active', 'owner', users_list)
    list_filter = ('active', 'owner')
    search_fields = ('number', 'description', 'owner__username')
    filter_horizontal = ('groups', 'users')  # funguje jen pokud pole groups a users existuje
    raw_id_fields = ('owner',)  # místo neexistujícího 'user'
    ordering = ('number',)
    fieldsets = (
        (None, {
            'fields': ('number', 'description', 'active', 'owner', 'groups', 'users')
        }),
    )

####################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Groups"
####################################################################################################
# Registrace modelu Group do admin rozhraní django
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'id')
    search_fields = ('name', 'description')


####################################################################################################
#POLOŽKA V ADMIN ROZHRANÍ "Rules"
####################################################################################################
# Registrace modelu Rule do admin rozhraní django
@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'active', 'id')
    list_filter = ('active',)
    search_fields = ('name', 'description')
    ordering = ('name',)
# Signály pro dashboard aplikaci
#from .models import PhoneNumber
#from django.db.models.signals import post_save
#from django.dispatch import receiver

# Při uložení PhoneNumber přidat vlastníka do uživatelů
# aby se vlastník automaticky stal uživatelem, který má přístup k číslu

#x@receiver(post_save, sender=PhoneNumber)
#def add_owner_to_users(sender, instance, created, **kwargs):
#    if instance.owner and instance.owner not in instance.users.all():
#        instance.users.add(instance.owner)


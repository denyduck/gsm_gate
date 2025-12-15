# tabulky pro ukládání čísel a jejich vlastností

from django.db import models
from django.contrib.auth.models import User


# tabulka pro skupiny čísel
class Group(models.Model):

    # název a popis skupiny
    name = models.CharField(max_length=100)
    # volitelný popis skupiny
    description = models.CharField(max_length=255, blank=True)


    # skupina může mít více uživatelů (sdílení)
    users = models.ManyToManyField(User, related_name='shared', blank=True)
    # zobrazení názvu skupiny
    def __str__(self):
        return self.name


# tabulka pro telefonní čísla
class PhoneNumber(models.Model):

    # vlastník čísla (ten, kdo číslo vytvořil)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_numbers')
    # číslo může mít více uživatelů (sdílení)
    users = models.ManyToManyField(User, related_name='shared_numbers', blank=True)

    # samotné číslo a jeho popis
    number = models.CharField(max_length=20)

    # volitelný popis čísla
    description = models.CharField(max_length=100, blank=True)

    # zda je číslo aktivní
    active = models.BooleanField(default=True)

    # číslo může být v jedné nebo více skupinách
    groups = models.ManyToManyField(Group, related_name='phone_numbers', blank=True)


    # zobrazení čísla jako textu
    def __str__(self):
        return self.number
    

# tabulka pro pravidla (pro budoucí použití)
class Rule(models.Model):
    # název pravidla
    name = models.CharField(max_length=100)
    # popis pravidla
    description = models.TextField(blank=True)
    # zda je pravidlo aktivní
    active = models.BooleanField(default=True)


    def __str__(self):
        return self.name
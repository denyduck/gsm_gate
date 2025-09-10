from django.db import models
from django.contrib.auth.models import User

class Group(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name

class PhoneNumber(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    number = models.CharField(max_length=20)
    description = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
  
    # číslo může být v jedné nebo více skupinách
    groups = models.ManyToManyField(Group, related_name='phone_numbers', blank=True)
    # číslo může mít více uživate
    users = models.ManyToManyField(User, related_name='phone_numbers', blank=True)
    

    def __str__(self):
        return self.number


class Rule(models.Model):
    name = models.CharField(max_length=100)
    condition = models.CharField(max_length=255)
    action = models.CharField(max_length=255)

    def __str__(self):
        return self.name
from django.db import models
from django.contrib.auth.models import User



class Invigilator(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name="invigilator")
    staff_id = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"{self.staff_id} - {self.full_name}"

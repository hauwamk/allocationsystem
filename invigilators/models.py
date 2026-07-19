from django.db import models



class Invigilator(models.Model):
    staff_id = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"{self.staff_id} - {self.full_name}"

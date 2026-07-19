from django.db import models


class Venue(models.Model):
    venue_name = models.CharField(max_length=50, unique=True)
    capacity = models.PositiveIntegerField()

    def __str__(self):
        return self.venue_name

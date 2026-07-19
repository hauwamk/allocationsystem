from django.forms import ModelForm
from .models import Venue

class VenueForm(ModelForm):
    class Meta:
        model = Venue
        fields = [
            "venue_name",
            "capacity",
        ]
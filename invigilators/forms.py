from django.forms import ModelForm

from .models import Invigilator


class InvigilatorForm(ModelForm):
    class Meta:
        model = Invigilator
        fields = ["staff_id", "full_name", "phone_number"]
from django import forms
from django.forms import ModelForm

from .models import Invigilator


class InvigilatorForm(ModelForm):
    class Meta:
        model = Invigilator
        fields = ["staff_id", "full_name", "phone_number"]


class InvigilatorImportForm(forms.Form):
    csv_file = forms.FileField(label='Select a CSV file')
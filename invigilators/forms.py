from django import forms
from django.forms import ModelForm

from exam.imports import tabular_upload_field
from .models import Invigilator


class InvigilatorForm(ModelForm):
    class Meta:
        model = Invigilator
        fields = ["staff_id", "full_name", "phone_number"]


class InvigilatorImportForm(forms.Form):
    csv_file = tabular_upload_field()
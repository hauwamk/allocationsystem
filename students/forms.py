from django import forms
from django.forms import ModelForm
from .models import Student
class StudentImportForm(forms.Form):
    csv_file = forms.FileField(label='Select a CSV file')

class StudentEditForm(ModelForm):
    class Meta:
        model = Student
        fields = ['registration_number', 'first_name', 'last_name', 'level','department', 'gender', 'email']

from django import forms
from django.forms import ModelForm
from .models import Student
from courses.models import Course


class StudentImportForm(forms.Form):
    csv_file = forms.FileField(label='Select a CSV file')


class StudentEditForm(ModelForm):
    class Meta:
        model = Student
        fields = ['registration_number', 'first_name', 'last_name', 'level', 'department', 'gender', 'email']


class RegisterCourseForm(forms.Form):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Courses",
    )
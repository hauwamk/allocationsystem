from django import forms
from django.forms import ModelForm
from exam.imports import tabular_upload_field
from .models import Course

class CourseForm(ModelForm):
    class Meta:
        model = Course
        fields = ['course_code', 'course_title','department', 'level', 'semester']


class CourseImportForm(forms.Form):
    csv_file = tabular_upload_field()
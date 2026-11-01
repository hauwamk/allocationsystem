from django import forms
from django.forms import ModelForm
from exam.imports import tabular_upload_field
from .models import Student
from courses.models import Course


class StudentImportForm(forms.Form):
    csv_file = tabular_upload_field()


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


class CourseListImportForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.all().order_by("course_code"),
        label="Course",
    )
    csv_file = tabular_upload_field(label="Student list (CSV or Excel)")
    replace_existing = forms.BooleanField(
        required=False,
        label="Replace the existing list for this course",
        help_text="Off = add these students and keep everyone already registered.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].label_from_instance = (
            lambda c: f"{c.course_code} - {c.course_title}"
        )
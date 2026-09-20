from django import forms
from django.forms import ModelForm
from .models import Exam, Timetable

class ExamForm(ModelForm):
    class Meta:
        model = Exam
        fields = [
            "course",
            "exam_date",
            "exam_time",
            "duration",
        ]


class TimetableForm(ModelForm):
    """Just asks for a name — status starts as DRAFT automatically."""
    class Meta:
        model = Timetable
        fields = ["name"]


class TimetableUploadForm(forms.Form):
    """CSV upload form for adding a batch of exams into a specific timetable."""
    csv_file = forms.FileField(label="Select a CSV file")
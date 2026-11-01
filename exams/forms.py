from django import forms
from django.forms import ModelForm
from exam.imports import tabular_upload_field
from exam.timetable_files import validate_timetable_file
from .models import Exam, Timetable

class ExamForm(ModelForm):
    class Meta:
        model = Exam
        fields = [
            "course",
            "timetable",
            "exam_date",
            "exam_time",
            "duration",
        ]
        help_texts = {
            "timetable": (
                "Choose the draft batch this exam belongs to. Exams outside a "
                "batch are hidden from students."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timetable"].required = False
        self.fields["timetable"].queryset = Timetable.objects.filter(status="DRAFT")
        self.fields["timetable"].empty_label = "No batch (hidden from students)"
        self.fields["course"].widget.attrs.update(
            {
                "data-searchable": "true",
                "data-search-placeholder": "Type to filter courses",
            }
        )


class TimetableForm(ModelForm):
    """Just asks for a name — status starts as DRAFT automatically."""
    class Meta:
        model = Timetable
        fields = ["name"]


class TimetableFileForm(forms.Form):
    """Receives the official timetable document itself, as a PDF or image."""
    source_file = forms.FileField(
        label="Timetable file",
        help_text="PDF, PNG, JPG or WEBP, up to 20 MB. PDFs may have up to 5 pages.",
        validators=[validate_timetable_file],
    )


class TimetableUploadForm(forms.Form):
    """CSV or Excel upload form for adding a batch of exams into a timetable."""
    csv_file = tabular_upload_field()
    replace_existing = forms.BooleanField(
        required=False,
        label="Replace the exams already in this batch",
        help_text=(
            "Choose this when the file is the complete list for the batch. "
            "You will see what will be added and removed before anything changes."
        ),
    )
from django.forms import ModelForm
from .models import Exam

class ExamForm(ModelForm):
    class Meta:
        model = Exam
        fields = [
            "course",
            "exam_date",
            "exam_time",
            "duration",
        ]
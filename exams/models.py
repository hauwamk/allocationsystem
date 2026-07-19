
from django.db import models
from courses.models import Course


class Exam(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    exam_date = models.DateField()
    exam_time = models.TimeField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")

    def __str__(self):
        return f"{self.course.course_code} - {self.exam_date}"

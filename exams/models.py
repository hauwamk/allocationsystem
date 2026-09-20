from django.db import models
from courses.models import Course


class Timetable(models.Model):
    """
    A named batch of exams (e.g. "2026 First Semester"), with a lifecycle:
    DRAFT while it's being built and checked for clashes, PUBLISHED once
    an officer confirms it's ready for students to see, ARCHIVED once
    that exam period is over.

    Students only ever see exams that belong to a PUBLISHED timetable.
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]

    name = models.CharField(max_length=100, help_text="e.g. '2026 First Semester'")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class Exam(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    exam_date = models.DateField()
    exam_time = models.TimeField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")

    # Nullable so existing exams created before this feature existed don't
    # break — those are treated as "always visible" to students.
    timetable = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, null=True, blank=True, related_name="exams"
    )

    def __str__(self):
        return f"{self.course.course_code} - {self.exam_date}"
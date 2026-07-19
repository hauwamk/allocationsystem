from django.db import models

class Course(models.Model):
    LEVEL_CHOICES = [
        ("100", "100 Level"),
        ("200", "200 Level"),
        ("300", "300 Level"),
        ("400", "400 Level"),
    ]
    DEPARTMENT_CHOICES = [
        ("CS", "Computer Science"),
        ("SE", "Software Engineering"),
        ("IT", "Information Technology"),
        ("CY", "Cyber Security"),
    ]

    SEMESTER_CHOICES = [
        ("First", "First Semester"),
        ("Second", "Second Semester"),
    ]

    course_code = models.CharField(max_length=10, unique=True)
    course_title = models.CharField(max_length=100)
    department = models.CharField(max_length=2, choices=DEPARTMENT_CHOICES)
    level = models.CharField(max_length=3, choices=LEVEL_CHOICES)
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)

    def __str__(self):
        return f"{self.course_code} - {self.course_title}"
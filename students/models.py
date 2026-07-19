from django.db import models
from courses.models import Course

class Student(models.Model):
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

    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
    ]

    registration_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    department = models.CharField(max_length=2, choices=DEPARTMENT_CHOICES)
    level = models.CharField(max_length=3, choices=LEVEL_CHOICES)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    email = models.EmailField(blank=True, null=True)

    def __str__(self):
        return f"{self.registration_number} - {self.first_name} {self.last_name}"


class Registration(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student.registration_number} - {self.course.course_code}"
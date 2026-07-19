
from django.db import models
from students.models import Student
from exams.models import Exam
from venues.models import Venue
from invigilators.models import Invigilator


class Allocation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    invigilator = models.ForeignKey(Invigilator, on_delete=models.CASCADE)
    seating_number = models.PositiveIntegerField()

    
    def __str__(self):
        return f"{self.student.registration_number} - {self.exam.course.course_code}"

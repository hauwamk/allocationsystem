from django.db import models
from students.models import Student
from exams.models import Exam
from venues.models import Venue
from invigilators.models import Invigilator

class ExamSession(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    invigilator = models.ForeignKey(Invigilator, on_delete=models.CASCADE)

    class Meta:  
        # One venue can't host two sessions for the *same* exam, and one  
        # invigilator can't be double-booked in the same session slot.  
        unique_together = ("exam", "venue")  

    def __str__(self):  
        return f"{self.exam.course.course_code} - {self.venue.venue_name}"

class Allocation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    exam_session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, null=True, blank=True)
    seating_number = models.PositiveIntegerField()

    class Meta:  
        unique_together = [  
            ("exam_session", "seating_number"),  # no two students share a seat  
            ("student", "exam_session"),          # a student isn't double-booked in one session  
        ]  

    def __str__(self):  
        return f"{self.student.registration_number} - {self.exam_session.exam.course.course_code}"
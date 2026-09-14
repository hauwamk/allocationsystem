
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import Course
from students.models import Student, Registration
from exams.models import Exam
from venues.models import Venue
from invigilators.models import Invigilator
from allocations.models import ExamSession, Allocation


class VenueRevealTests(TestCase):
    def setUp(self):
        # A student with a working login, same as the real system creates
        # via add_student / import_students.
        self.user = User.objects.create_user(username="STU001", password="STU001")
        self.student = Student.objects.create(
            user=self.user, registration_number="STU001", first_name="Test", last_name="Student",
            department="CS", level="200", gender="M",
        )
        self.course = Course.objects.create(
            course_code="CS200", course_title="Test Course", department="CS", level="200", semester="First",
        )
        Registration.objects.create(student=self.student, course=self.course)

        self.venue = Venue.objects.create(venue_name="Hall A", capacity=50)
        self.invigilator = Invigilator.objects.create(staff_id="STF001", full_name="Test Invigilator")

        self.client.login(username="STU001", password="STU001")

    def _allocate_exam_at(self, when):
        """Helper: creates an Exam at a given datetime, with this student seated in it."""
        exam = Exam.objects.create(
            course=self.course, exam_date=when.date(), exam_time=when.time(), duration=120,
        )
        session = ExamSession.objects.create(exam=exam, venue=self.venue, invigilator=self.invigilator)
        Allocation.objects.create(student=self.student, exam_session=session, seating_number=1)
        return exam

    def test_venue_hidden_more_than_one_hour_before_exam(self):
        # Exam is 3 hours away — too early, venue should stay hidden.
        self._allocate_exam_at(timezone.now() + timedelta(hours=3))

        response = self.client.get(reverse("student_dashboard"))

        self.assertContains(response, "You can check your examination venue 1 hour before the exam.")
        self.assertNotContains(response, "Hall A")

    def test_venue_visible_within_one_hour_of_exam(self):
        # Exam is 30 minutes away — within the reveal window, venue should show.
        self._allocate_exam_at(timezone.now() + timedelta(minutes=30))

        response = self.client.get(reverse("student_dashboard"))

        self.assertContains(response, "Hall A")


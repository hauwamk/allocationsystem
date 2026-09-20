from datetime import date, time

from django.test import TestCase

from courses.models import Course
from students.models import Student, Registration
from exams.models import Exam
from venues.models import Venue
from invigilators.models import Invigilator
from allocations.services import allocate_exam
from allocations.models import ExamSession


class LoadBalancingTests(TestCase):
    def setUp(self):
        # Two venues, two invigilators, deliberately more than one exam
        # needs, so we can prove the SECOND exam doesn't just reuse the
        # exact same venue/invigilator as the first.
        self.venue_a = Venue.objects.create(venue_name="Hall A", capacity=50)
        self.venue_b = Venue.objects.create(venue_name="Hall B", capacity=50)
        self.invigilator_a = Invigilator.objects.create(staff_id="STF001", full_name="Invigilator A")
        self.invigilator_b = Invigilator.objects.create(staff_id="STF002", full_name="Invigilator B")

        self.course_a = Course.objects.create(
            course_code="CSA200", course_title="Course A", department="CS", level="200", semester="First",
        )
        self.course_b = Course.objects.create(
            course_code="CSB200", course_title="Course B", department="CS", level="200", semester="First",
        )

        student_a = Student.objects.create(
            registration_number="CS/200/001", first_name="A", last_name="Student",
            department="CS", level="200", gender="M",
        )
        student_b = Student.objects.create(
            registration_number="CS/200/002", first_name="B", last_name="Student",
            department="CS", level="200", gender="F",
        )
        Registration.objects.create(student=student_a, course=self.course_a)
        Registration.objects.create(student=student_b, course=self.course_b)

    def test_second_exam_does_not_reuse_same_venue_and_invigilator(self):
        # Two exams at DIFFERENT times, so nothing forces them apart by
        # the busy-check alone — load balancing is what should separate them.
        exam_a = Exam.objects.create(
            course=self.course_a, exam_date=date(2026, 12, 1), exam_time=time(9, 0), duration=120,
        )
        exam_b = Exam.objects.create(
            course=self.course_b, exam_date=date(2026, 12, 1), exam_time=time(14, 0), duration=120,
        )

        allocate_exam(exam_a)
        allocate_exam(exam_b)

        session_a = ExamSession.objects.get(exam=exam_a)
        session_b = ExamSession.objects.get(exam=exam_b)

        self.assertNotEqual(session_a.venue_id, session_b.venue_id)
        self.assertNotEqual(session_a.invigilator_id, session_b.invigilator_id)

# Create your tests here.

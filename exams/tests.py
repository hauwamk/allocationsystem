from datetime import date, time

from django.test import TestCase

from courses.models import Course
from students.models import Student, Registration
from exams.models import Exam
from exams.clash_service import find_clashes


class ClashDetectionTests(TestCase):
    def setUp(self):
        # One student registered for two different courses, so we can
        # engineer both a clashing and a non-clashing scenario.
        self.student = Student.objects.create(
            registration_number="CS/200/001", first_name="Test", last_name="Student",
            department="CS", level="200", gender="M",
        )
        self.course_a = Course.objects.create(
            course_code="CSA200", course_title="Course A", department="CS", level="200", semester="First",
        )
        self.course_b = Course.objects.create(
            course_code="CSB200", course_title="Course B", department="CS", level="200", semester="First",
        )
        Registration.objects.create(student=self.student, course=self.course_a)
        Registration.objects.create(student=self.student, course=self.course_b)

    def test_detects_clash_when_two_registered_courses_share_a_slot(self):
        # Both exams on the same date and time — this student can't sit both.
        exam_a = Exam.objects.create(
            course=self.course_a, exam_date=date(2026, 12, 1), exam_time=time(9, 0), duration=120,
        )
        exam_b = Exam.objects.create(
            course=self.course_b, exam_date=date(2026, 12, 1), exam_time=time(9, 0), duration=120,
        )

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 1)
        self.assertEqual(clashes[0]["student"], self.student)
        self.assertEqual(clashes[0]["exam_b"], exam_b)

    def test_no_clash_when_exams_are_at_different_times(self):
        exam_a = Exam.objects.create(
            course=self.course_a, exam_date=date(2026, 12, 1), exam_time=time(9, 0), duration=120,
        )
        Exam.objects.create(
            course=self.course_b, exam_date=date(2026, 12, 1), exam_time=time(14, 0), duration=120,
        )

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 0)


from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from courses.models import Course
from students.models import Student, Registration
from exams.models import Exam, Timetable
from venues.models import Venue
from invigilators.models import Invigilator
from allocations.services import allocate_exam
from allocations.models import Allocation, ExamSession


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


class RandomStudentAllocationTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(venue_name="Hall A", capacity=4)
        self.invigilator = Invigilator.objects.create(
            staff_id="STF001", full_name="Invigilator A"
        )
        self.course = Course.objects.create(
            course_code="CSC300",
            course_title="Algorithms",
            department="CS",
            level="300",
            semester="First",
        )

        for number in range(1, 5):
            student = Student.objects.create(
                registration_number=f"CS/300/{number:03d}",
                first_name=f"Student {number}",
                last_name="Test",
                department="CS",
                level="300",
                gender="M",
            )
            Registration.objects.create(student=student, course=self.course)

        self.exam = Exam.objects.create(
            course=self.course,
            exam_date=date(2026, 12, 1),
            exam_time=time(9, 0),
            duration=120,
        )

    @patch("allocations.services.random.shuffle")
    def test_students_are_shuffled_before_seating(self, shuffle):
        shuffle.side_effect = lambda students: students.reverse()

        allocate_exam(self.exam)

        session = ExamSession.objects.get(exam=self.exam)
        seated = list(
            Allocation.objects.filter(exam_session=session)
            .order_by("seating_number")
            .values_list("student__registration_number", flat=True)
        )

        self.assertEqual(
            seated,
            ["CS/300/004", "CS/300/003", "CS/300/002", "CS/300/001"],
        )
        shuffle.assert_called_once()


class VenueFitTests(TestCase):
    def setUp(self):
        # The big hall is created last so ordering can't accidentally come
        # from creation order rather than from the fit rule.
        self.small = Venue.objects.create(venue_name="Small Room", capacity=20)
        self.large = Venue.objects.create(venue_name="Big Hall", capacity=120)
        Invigilator.objects.create(staff_id="STF001", full_name="Invigilator A")
        self.course = Course.objects.create(
            course_code="CSC100",
            course_title="Intro",
            department="CS",
            level="100",
            semester="First",
        )
        for number in range(1, 6):
            student = Student.objects.create(
                registration_number=f"CS/100/{number:03d}",
                first_name=f"Student {number}",
                last_name="Test",
                department="CS",
                level="100",
                gender="M",
            )
            Registration.objects.create(student=student, course=self.course)
        self.exam = Exam.objects.create(
            course=self.course,
            exam_date=date(2026, 12, 2),
            exam_time=time(9, 0),
            duration=120,
        )

    def test_smallest_venue_that_fits_the_group_wins(self):
        allocate_exam(self.exam)

        session = ExamSession.objects.get(exam=self.exam)
        self.assertEqual(session.venue, self.small)
        self.assertEqual(Allocation.objects.filter(exam_session=session).count(), 5)


class AllocationViewMethodTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        course = Course.objects.create(
            course_code="CSC101",
            course_title="Intro",
            department="CS",
            level="100",
            semester="First",
        )
        student = Student.objects.create(
            registration_number="CS/100/001",
            first_name="Student",
            last_name="Test",
            department="CS",
            level="100",
            gender="M",
        )
        Registration.objects.create(student=student, course=course)
        self.exam = Exam.objects.create(
            course=course,
            exam_date=date(2026, 12, 3),
            exam_time=time(9, 0),
            duration=120,
        )
        Venue.objects.create(venue_name="Hall A", capacity=20)
        Invigilator.objects.create(staff_id="STF001", full_name="Invigilator A")

    def test_allocating_an_exam_requires_a_post(self):
        response = self.client.get(reverse("allocate_exam", args=[self.exam.id]))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ExamSession.objects.filter(exam=self.exam).exists())

    def test_allocating_all_exams_requires_a_post(self):
        response = self.client.get(reverse("allocate_all_exams"))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ExamSession.objects.exists())

    def test_posting_an_allocation_seats_the_registered_students(self):
        response = self.client.post(reverse("allocate_exam", args=[self.exam.id]))

        self.assertRedirects(response, reverse("exam_list"))
        session = ExamSession.objects.get(exam=self.exam)
        self.assertEqual(Allocation.objects.filter(exam_session=session).count(), 1)

    def test_allocate_all_only_touches_draft_batch_exams(self):
        timetable = Timetable.objects.create(name="2027 First Semester")
        batch_exam = Exam.objects.create(
            course=self.exam.course,
            exam_date=date(2026, 12, 5),
            exam_time=time(9, 0),
            duration=120,
            timetable=timetable,
        )

        self.client.post(reverse("allocate_all_exams"))

        self.assertTrue(ExamSession.objects.filter(exam=batch_exam).exists())
        self.assertFalse(ExamSession.objects.filter(exam=self.exam).exists())


class OverlapAllocationTests(TestCase):
    """An exam occupies its start time plus its duration, not just its start."""

    def setUp(self):
        self.venue = Venue.objects.create(venue_name="Only Hall", capacity=50)
        self.invigilator = Invigilator.objects.create(
            staff_id="STF001", full_name="Only Invigilator"
        )
        self.course_a = Course.objects.create(
            course_code="CSA400", course_title="Course A", department="CS",
            level="400", semester="First",
        )
        self.course_b = Course.objects.create(
            course_code="CSB400", course_title="Course B", department="CS",
            level="400", semester="First",
        )
        for number, course in enumerate((self.course_a, self.course_b), start=1):
            student = Student.objects.create(
                registration_number=f"CS/400/{number:03d}", first_name="Test",
                last_name="Student", department="CS", level="400", gender="M",
            )
            Registration.objects.create(student=student, course=course)

        self.exam_a = Exam.objects.create(
            course=self.course_a, exam_date=date(2026, 12, 1),
            exam_time=time(9, 0), duration=120,
        )
        allocate_exam(self.exam_a)

    def _exam_b(self, start):
        return Exam.objects.create(
            course=self.course_b, exam_date=date(2026, 12, 1),
            exam_time=start, duration=60,
        )

    def test_overlapping_exam_cannot_use_the_busy_venue(self):
        exam_b = self._exam_b(time(10, 0))

        with self.assertRaisesMessage(ValueError, "could not be seated"):
            allocate_exam(exam_b)

        self.assertFalse(ExamSession.objects.filter(exam=exam_b).exists())

    def test_back_to_back_exam_can_use_the_same_venue(self):
        exam_b = self._exam_b(time(11, 0))

        allocate_exam(exam_b)

        self.assertEqual(ExamSession.objects.get(exam=self.exam_a).venue, self.venue)
        self.assertEqual(ExamSession.objects.get(exam=exam_b).venue, self.venue)


class RemoveAllocationTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        Venue.objects.create(venue_name="Hall A", capacity=20)
        Invigilator.objects.create(staff_id="STF001", full_name="Invigilator A")
        course = Course.objects.create(
            course_code="CSC300",
            course_title="Algorithms",
            department="CS",
            level="300",
            semester="First",
        )
        for number in range(1, 4):
            student = Student.objects.create(
                registration_number=f"CS/300/{number:03d}",
                first_name=f"Student {number}",
                last_name="Test",
                department="CS",
                level="300",
                gender="M",
            )
            Registration.objects.create(student=student, course=course)
        exam = Exam.objects.create(
            course=course,
            exam_date=date(2026, 12, 4),
            exam_time=time(9, 0),
            duration=120,
        )
        allocate_exam(exam)
        self.session = ExamSession.objects.get(exam=exam)
        self.allocation = Allocation.objects.get(
            exam_session=self.session, seating_number=2
        )

    def test_removing_one_seat_leaves_the_rest_of_the_chart(self):
        response = self.client.post(
            reverse("remove_allocation", args=[self.allocation.id])
        )

        self.assertRedirects(
            response, reverse("session_detail", args=[self.session.id])
        )
        self.assertFalse(Allocation.objects.filter(id=self.allocation.id).exists())
        self.assertEqual(
            Allocation.objects.filter(exam_session=self.session).count(), 2
        )

    def test_removing_a_seat_requires_a_post(self):
        response = self.client.get(
            reverse("remove_allocation", args=[self.allocation.id])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Allocation.objects.filter(id=self.allocation.id).exists())


class ClearExamAllocationTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        Venue.objects.create(venue_name="Hall A", capacity=50)
        Venue.objects.create(venue_name="Hall B", capacity=50)
        Invigilator.objects.create(staff_id="STF001", full_name="Invigilator A")
        Invigilator.objects.create(staff_id="STF002", full_name="Invigilator B")

        student = Student.objects.create(
            registration_number="CS/300/001",
            first_name="Student",
            last_name="Test",
            department="CS",
            level="300",
            gender="M",
        )
        course_a = Course.objects.create(
            course_code="CSA300",
            course_title="Course A",
            department="CS",
            level="300",
            semester="First",
        )
        course_b = Course.objects.create(
            course_code="CSB300",
            course_title="Course B",
            department="CS",
            level="300",
            semester="First",
        )
        Registration.objects.create(student=student, course=course_a)
        Registration.objects.create(student=student, course=course_b)

        self.exam_a = Exam.objects.create(
            course=course_a,
            exam_date=date(2026, 12, 4),
            exam_time=time(9, 0),
            duration=120,
        )
        self.exam_b = Exam.objects.create(
            course=course_b,
            exam_date=date(2026, 12, 5),
            exam_time=time(9, 0),
            duration=120,
        )
        allocate_exam(self.exam_a)
        allocate_exam(self.exam_b)

    def test_clearing_an_exam_leaves_other_exams_seated(self):
        response = self.client.post(
            reverse("clear_exam_allocation", args=[self.exam_a.id])
        )

        self.assertRedirects(response, reverse("exam_list"))
        self.assertFalse(ExamSession.objects.filter(exam=self.exam_a).exists())
        self.assertFalse(
            Allocation.objects.filter(exam_session__exam=self.exam_a).exists()
        )
        self.assertTrue(ExamSession.objects.filter(exam=self.exam_b).exists())
        self.assertTrue(
            Allocation.objects.filter(exam_session__exam=self.exam_b).exists()
        )

    def test_clearing_seating_requires_a_post(self):
        response = self.client.get(
            reverse("clear_exam_allocation", args=[self.exam_a.id])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(ExamSession.objects.filter(exam=self.exam_a).exists())

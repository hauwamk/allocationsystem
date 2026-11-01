import datetime

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from allocations.models import Allocation, ExamSession
from courses.models import Course
from exams.models import Exam
from invigilators.models import Invigilator
from venues.models import Venue

from .models import Registration, Student


class ImportStudentsTests(TestCase):
    def setUp(self):
        # import_students is protected by @staff_required, so the test
        # client needs to be logged in as a staff account to reach it.
        self.staff_user = User.objects.create_user(username="officer", password="testpass123", is_staff=True)
        self.client.login(username="officer", password="testpass123")

    def test_import_accepts_common_header_names(self):
        csv_content = (
            "Registration Number,First Name,Last Name,Level,Department,Gender,Email\n"
            "ABC123,Jane,Doe,300,CS,F,jane@example.com\n"
        )
        upload = SimpleUploadedFile(
            "students.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("import_students"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        student = Student.objects.filter(registration_number="ABC123").first()
        self.assertIsNotNone(student)
        self.assertEqual(student.department, "CS")
        self.assertIsNotNone(student.user)
        self.assertEqual(student.user.username, "ABC123")
        self.assertTrue(student.user.check_password("ABC123"))

    def test_import_links_login_for_existing_student_without_user(self):
        Student.objects.create(
            registration_number="EXIST123",
            first_name="Existing",
            last_name="Student",
            department="COM",
            level="300",
            gender="F",
            email="existing@example.com",
        )
        csv_content = (
            "registration_number,first_name,last_name,level,department,gender,email\n"
            "EXIST123,Existing,Student,300,COM,F,existing@example.com\n"
        )
        upload = SimpleUploadedFile(
            "students.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("import_students"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(registration_number="EXIST123")
        self.assertIsNotNone(student.user)
        self.assertEqual(student.user.username, "EXIST123")
        self.assertTrue(student.user.check_password("EXIST123"))


class RegistrationImportReplaceTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")

        self.course = Course.objects.create(
            course_code="CS101",
            course_title="Mathematics I",
            department="COM",
            level="100",
            semester="First",
        )
        self.alice = Student.objects.create(
            registration_number="CS/100/001",
            first_name="Alice",
            last_name="Adams",
            department="COM",
            level="100",
            gender="F",
        )
        self.bob = Student.objects.create(
            registration_number="CS/100/002",
            first_name="Bob",
            last_name="Brown",
            department="COM",
            level="100",
            gender="M",
        )
        self.carol = Student.objects.create(
            registration_number="CS/100/003",
            first_name="Carol",
            last_name="Clark",
            department="COM",
            level="100",
            gender="F",
        )
        Registration.objects.create(student=self.alice, course=self.course)
        Registration.objects.create(student=self.bob, course=self.course)

    def _upload(self, rows, replace=True):
        lines = ["Reg No,Full Name"]
        lines.extend(f"{reg_no},{full_name}" for reg_no, full_name in rows)
        upload = SimpleUploadedFile(
            "registrations.csv",
            ("\n".join(lines) + "\n").encode("utf-8"),
            content_type="text/csv",
        )
        data = {"course": self.course.id, "csv_file": upload}
        if replace:
            data["replace_existing"] = "on"
        return self.client.post(reverse("import_registrations"), data, follow=True)

    def _registrations(self):
        return set(
            Registration.objects.filter(course=self.course)
            .values_list("student_id", flat=True)
        )

    def test_replace_with_no_matched_rows_leaves_the_list_untouched(self):
        response = self._upload([("WRONG/FORMAT/999", "Nobody Here")])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})
        self.assertIsNone(response.context["preview"])
        self.assertTrue(response.context["summary"]["no_match"])
        self.assertNotIn("pending_registration_replace", self.client.session)

    def test_replace_shows_a_preview_before_anything_changes(self):
        response = self._upload(
            [("CS/100/001", "Alice Adams"), ("CS/100/003", "Carol Clark")]
        )

        self.assertEqual(response.status_code, 200)
        preview = response.context["preview"]
        self.assertEqual(preview["added"], 1)
        self.assertEqual(preview["removed"], 1)
        self.assertEqual([s.id for s in preview["to_remove"]], [self.bob.id])
        # Nothing has been applied yet.
        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})
        self.assertIn("pending_registration_replace", self.client.session)

    def test_confirming_the_preview_applies_the_exact_add_and_remove_sets(self):
        self._upload(
            [("CS/100/001", "Alice Adams"), ("CS/100/003", "Carol Clark")]
        )

        response = self.client.post(
            reverse("confirm_registration_replace"), {"action": "confirm"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._registrations(), {self.alice.id, self.carol.id})
        self.assertNotIn("pending_registration_replace", self.client.session)
        self.assertContains(response, "added 1, removed 1")

    def test_cancelling_the_preview_leaves_the_list_untouched(self):
        self._upload([("CS/100/001", "Alice Adams")])

        response = self.client.post(
            reverse("confirm_registration_replace"), {"action": "cancel"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})
        self.assertNotIn("pending_registration_replace", self.client.session)

    def test_a_misspelled_reg_number_is_visible_before_it_removes_a_student(self):
        # Bob is registered, but his reg number is mistyped in the file.
        response = self._upload(
            [("CS/100/001", "Alice Adams"), ("CS/100/002X", "Bob Brown")]
        )

        preview = response.context["preview"]
        self.assertEqual([s.id for s in preview["to_remove"]], [self.bob.id])
        self.assertEqual([reg for reg, _ in preview["unknown"]], ["CS/100/002X"])
        # Still registered: the officer can see the mistake and cancel.
        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})

    def test_confirm_is_refused_if_no_preview_is_waiting(self):
        response = self.client.post(
            reverse("confirm_registration_replace"), {"action": "confirm"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})

    def test_confirm_is_refused_if_seats_were_allocated_after_the_preview(self):
        self._upload([("CS/100/001", "Alice Adams")])

        exam = Exam.objects.create(
            course=self.course,
            exam_date=datetime.date(2026, 12, 1),
            exam_time=datetime.time(9, 0),
            duration=120,
        )
        venue = Venue.objects.create(venue_name="Hall A", capacity=50)
        invigilator = Invigilator.objects.create(
            staff_id="INV001", full_name="Invigilator One"
        )
        exam_session = ExamSession.objects.create(
            exam=exam, venue=venue, invigilator=invigilator
        )
        Allocation.objects.create(
            student=self.alice, exam_session=exam_session, seating_number=1
        )

        self.client.post(
            reverse("confirm_registration_replace"), {"action": "confirm"}, follow=True
        )

        self.assertEqual(self._registrations(), {self.alice.id, self.bob.id})
        self.assertNotIn("pending_registration_replace", self.client.session)
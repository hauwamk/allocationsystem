import shutil
import tempfile
from datetime import date, time, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from courses.models import Course
from students.models import Student, Registration
from exams.models import Exam, Timetable
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
        self.timetable = Timetable.objects.create(
            name="2027 First Semester", status="PUBLISHED"
        )

        self.client.login(username="STU001", password="STU001")

    def _allocate_exam_at(self, when):
        """Helper: creates an Exam at a given datetime, with this student seated in it."""
        exam = Exam.objects.create(
            course=self.course, exam_date=when.date(), exam_time=when.time(),
            duration=120, timetable=self.timetable,
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


class TimetableImageDownloadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="STU002", password="STU002")
        self.student = Student.objects.create(
            user=self.user, registration_number="STU/002", first_name="Image",
            last_name="Student", department="CS", level="300", gender="F",
        )
        self.course = Course.objects.create(
            course_code="CS301", course_title="Software Design", department="CS",
            level="300", semester="First",
        )
        Registration.objects.create(student=self.student, course=self.course)

        self.venue = Venue.objects.create(venue_name="Lecture Room 1", capacity=40)
        self.invigilator = Invigilator.objects.create(
            staff_id="STF002", full_name="Second Invigilator"
        )
        self.timetable = Timetable.objects.create(
            name="2027 First Semester", status="PUBLISHED"
        )
        self.client.login(username="STU002", password="STU002")

    def _seat_student(self, when):
        exam = Exam.objects.create(
            course=self.course, exam_date=when.date(), exam_time=when.time(),
            duration=120, timetable=self.timetable,
        )
        session = ExamSession.objects.create(
            exam=exam, venue=self.venue, invigilator=self.invigilator
        )
        Allocation.objects.create(
            student=self.student, exam_session=session, seating_number=3
        )

    def test_downloading_png_returns_a_png_image(self):
        self._seat_student(timezone.now() + timedelta(minutes=30))

        response = self.client.get(
            reverse("student_timetable_image", args=["png"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.png"'))

        image = Image.open(BytesIO(response.content))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.width, 1600)

    def test_downloading_jpg_returns_a_jpeg_image(self):
        self._seat_student(timezone.now() + timedelta(minutes=30))

        response = self.client.get(
            reverse("student_timetable_image", args=["jpg"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(Image.open(BytesIO(response.content)).format, "JPEG")

    def test_jpeg_alias_is_accepted(self):
        response = self.client.get(
            reverse("student_timetable_image", args=["jpeg"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_unknown_format_is_rejected(self):
        response = self.client.get(
            reverse("student_timetable_image", args=["gif"])
        )

        self.assertEqual(response.status_code, 404)

    def test_image_renders_while_the_venue_is_still_hidden(self):
        self._seat_student(timezone.now() + timedelta(hours=5))

        response = self.client.get(
            reverse("student_timetable_image", args=["png"])
        )

        self.assertEqual(response.status_code, 200)
        Image.open(BytesIO(response.content)).verify()

    def test_image_renders_with_no_exams(self):
        response = self.client.get(
            reverse("student_timetable_image", args=["png"])
        )

        self.assertEqual(response.status_code, 200)
        Image.open(BytesIO(response.content)).verify()


class StudentPrintTimetableTests(TestCase):
    """The printable timetable shows only code, title, date and time."""

    def setUp(self):
        self.user = User.objects.create_user(username="STU005", password="STU005")
        self.student = Student.objects.create(
            user=self.user, registration_number="STU/005", first_name="Print",
            last_name="Student", department="CS", level="200", gender="M",
        )
        self.course = Course.objects.create(
            course_code="CS205", course_title="Software Engineering", department="CS",
            level="200", semester="First",
        )
        Registration.objects.create(student=self.student, course=self.course)

        self.timetable = Timetable.objects.create(
            name="2027 First Semester", status="PUBLISHED"
        )
        self.venue = Venue.objects.create(venue_name="Print Hall", capacity=50)
        self.invigilator = Invigilator.objects.create(
            staff_id="STF005", full_name="Print Invigilator"
        )
        self.client.login(username="STU005", password="STU005")

    def _seat_student(self):
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=self.timetable,
        )
        session = ExamSession.objects.create(
            exam=exam, venue=self.venue, invigilator=self.invigilator
        )
        Allocation.objects.create(
            student=self.student, exam_session=session, seating_number=7
        )

    def test_print_page_shows_only_the_four_columns(self):
        self._seat_student()

        response = self.client.get(reverse("student_timetable_print"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CS205")
        self.assertContains(response, "Software Engineering")
        self.assertContains(response, "Jan. 11, 2027")
        self.assertContains(response, "9:00 a.m.")
        self.assertEqual(response.content.decode().count("<th>"), 4)

    def test_print_page_does_not_show_venue_seat_or_status(self):
        self._seat_student()

        response = self.client.get(reverse("student_timetable_print"))

        self.assertNotContains(response, "Print Hall")
        self.assertNotContains(response, "Seat No.")
        self.assertNotContains(response, "Not yet allocated")
        self.assertNotContains(response, "Available 1 hour before exam")
        self.assertNotContains(response, "Upcoming")

    def test_exams_on_the_same_day_are_ordered_by_time(self):
        later_course = Course.objects.create(
            course_code="CS206", course_title="Later Course", department="CS",
            level="200", semester="First",
        )
        Registration.objects.create(student=self.student, course=later_course)
        self._seat_student()
        Exam.objects.create(
            course=later_course, exam_date=date(2027, 1, 11),
            exam_time=time(11, 0), duration=120, timetable=self.timetable,
        )

        response = self.client.get(reverse("student_timetable_print"))

        content = response.content.decode()
        self.assertLess(content.index("CS205"), content.index("CS206"))

    def test_print_page_renders_an_empty_state_with_no_exams(self):
        response = self.client.get(reverse("student_timetable_print"))

        self.assertContains(response, "You currently have no scheduled examinations.")
        self.assertNotContains(response, "<table>")


class OfficialTimetableDownloadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.addCleanup(self.override.disable)

        self.user = User.objects.create_user(username="STU003", password="STU003")
        self.student = Student.objects.create(
            user=self.user, registration_number="STU/003", first_name="Official",
            last_name="Student", department="CS", level="200", gender="F",
        )
        self.client.login(username="STU003", password="STU003")

        self.timetable = Timetable.objects.create(
            name="2027 First Semester", status="PUBLISHED"
        )
        self.timetable.source_file.save(
            "official.png", ContentFile(self._png_bytes()), save=True
        )

    @staticmethod
    def _png_bytes():
        buffer = BytesIO()
        Image.new("RGB", (1000, 500), "white").save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _pdf_bytes(pages=2):
        buffer = BytesIO()
        first = Image.new("RGB", (600, 300), "white")
        extra = [Image.new("RGB", (600, 300), "white") for _ in range(pages - 1)]
        first.save(buffer, format="PDF", save_all=True, append_images=extra)
        return buffer.getvalue()

    def _pdf_timetable(self):
        timetable = Timetable.objects.create(
            name="2027 Second Semester", status="PUBLISHED"
        )
        timetable.source_file.save(
            "official.pdf", ContentFile(self._pdf_bytes()), save=True
        )
        return timetable

    def _download(self, timetable, image_format):
        return self.client.get(
            reverse(
                "student_official_timetable_download",
                args=[timetable.id, image_format],
            )
        )

    def test_published_timetable_appears_on_the_official_page(self):
        response = self.client.get(reverse("student_official_timetables"))

        self.assertContains(response, "2027 First Semester")

    def test_draft_timetable_is_not_listed(self):
        Timetable.objects.create(name="Secret Draft", status="DRAFT")

        response = self.client.get(reverse("student_official_timetables"))

        self.assertNotContains(response, "Secret Draft")

    def test_published_timetable_without_a_file_is_not_listed(self):
        Timetable.objects.create(name="No Document", status="PUBLISHED")

        response = self.client.get(reverse("student_official_timetables"))

        self.assertNotContains(response, "No Document")

    def test_downloading_an_uploaded_image_as_png(self):
        response = self._download(self.timetable, "png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn(
            'filename="2027-first-semester.png"', response["Content-Disposition"]
        )

        image = Image.open(BytesIO(response.content))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.width, 1000)

    def test_downloading_an_uploaded_image_as_jpg(self):
        response = self._download(self.timetable, "jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(Image.open(BytesIO(response.content)).format, "JPEG")

    def test_downloading_a_pdf_renders_and_stacks_its_pages(self):
        timetable = self._pdf_timetable()

        response = self._download(timetable, "png")

        self.assertEqual(response.status_code, 200)
        image = Image.open(BytesIO(response.content))
        self.assertEqual(image.format, "PNG")
        self.assertGreaterEqual(image.width, 1500)
        # Two pages of 600x300pt rendered above the 1600px width of one page.
        self.assertGreater(image.height, 1500)

    def test_draft_timetable_cannot_be_downloaded(self):
        draft = Timetable.objects.create(name="Draft 2028", status="DRAFT")
        draft.source_file.save(
            "draft.png", ContentFile(self._png_bytes()), save=True
        )

        response = self._download(draft, "png")

        self.assertEqual(response.status_code, 404)

    def test_timetable_without_a_file_returns_404(self):
        empty = Timetable.objects.create(name="Empty Published", status="PUBLISHED")

        response = self._download(empty, "png")

        self.assertEqual(response.status_code, 404)

    def test_unknown_format_is_rejected(self):
        response = self._download(self.timetable, "gif")

        self.assertEqual(response.status_code, 404)

    def test_staff_without_a_student_profile_is_redirected(self):
        User.objects.create_user(
            username="officer2", password="testpass123", is_staff=True
        )
        self.client.login(username="officer2", password="testpass123")

        response = self.client.get(reverse("student_official_timetables"))

        self.assertRedirects(response, reverse("students_list"))


class StudentTimetableVisibilityTests(TestCase):
    """Students only see exams that belong to a published batch."""

    def setUp(self):
        self.user = User.objects.create_user(username="STU004", password="STU004")
        self.student = Student.objects.create(
            user=self.user, registration_number="STU/004", first_name="Visibility",
            last_name="Student", department="CS", level="200", gender="M",
        )
        self.course = Course.objects.create(
            course_code="CS204", course_title="Visibility", department="CS",
            level="200", semester="First",
        )
        Registration.objects.create(student=self.student, course=self.course)
        self.client.login(username="STU004", password="STU004")

    def _exam(self, timetable):
        return Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=timetable,
        )

    def _exam_rows(self):
        response = self.client.get(reverse("student_dashboard"))
        return response.context["exam_rows"]

    def test_standalone_exam_is_hidden(self):
        self._exam(None)

        self.assertEqual(self._exam_rows(), [])

    def test_draft_batch_exam_is_hidden(self):
        self._exam(Timetable.objects.create(name="Secret Draft", status="DRAFT"))

        self.assertEqual(self._exam_rows(), [])

    def test_published_batch_exam_is_visible(self):
        exam = self._exam(Timetable.objects.create(name="Live", status="PUBLISHED"))

        self.assertEqual([row["exam"] for row in self._exam_rows()], [exam])


class ExamOfficerManagementTests(TestCase):
    """Creation and management of Exam Officer accounts."""

    def setUp(self):
        self.superadmin = User.objects.create_user(
            username="_superadmin_test",
            password="SuperPass!234",
            is_staff=True,
            is_superuser=True,
        )
        self.officer = User.objects.create_user(
            username="_officer_test",
            password="OfficerPass!234",
            is_staff=True,
        )

    def test_anonymous_management_redirects_to_superadmin_login(self):
        response = self.client.get(reverse("exam_officer_list"))

        self.assertRedirects(
            response,
            reverse("superadmin_login") + "?next=" + reverse("exam_officer_list"),
            fetch_redirect_response=False,
        )

    def test_logged_in_officer_is_denied_management(self):
        self.client.force_login(self.officer)

        response = self.client.get(reverse("exam_officer_list"))

        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_view_officer_list(self):
        self.client.force_login(self.superadmin)

        response = self.client.get(reverse("exam_officer_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.officer.username)

    def test_superadmin_login_redirects_to_next(self):
        response = self.client.post(reverse("superadmin_login"), {
            "username": self.superadmin.username,
            "password": "SuperPass!234",
            "next": reverse("exam_officer_list"),
        })

        self.assertRedirects(
            response, reverse("exam_officer_list"), fetch_redirect_response=False
        )

    def test_creation_marks_account_as_staff_not_superuser(self):
        self.client.force_login(self.superadmin)

        response = self.client.post(reverse("create_exam_officer"), {
            "username": "_created_officer",
            "password1": "CreatedPass!234",
            "password2": "CreatedPass!234",
        })

        self.assertRedirects(
            response, reverse("exam_officer_list"), fetch_redirect_response=False
        )
        created = User.objects.get(username="_created_officer")
        self.assertTrue(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertTrue(created.is_active)

    def test_superadmin_can_disable_and_enable_an_officer(self):
        self.client.force_login(self.superadmin)

        self.client.post(
            reverse("toggle_exam_officer_active", args=[self.officer.id])
        )
        self.officer.refresh_from_db()
        self.assertFalse(self.officer.is_active)

        self.client.post(
            reverse("toggle_exam_officer_active", args=[self.officer.id])
        )
        self.officer.refresh_from_db()
        self.assertTrue(self.officer.is_active)

    def test_a_disabled_officer_cannot_sign_in(self):
        self.officer.is_active = False
        self.officer.save(update_fields=["is_active"])

        logged_in = self.client.login(
            username=self.officer.username, password="OfficerPass!234"
        )

        self.assertFalse(logged_in)

    def test_toggle_cannot_target_a_superadmin(self):
        self.client.force_login(self.superadmin)

        response = self.client.post(
            reverse("toggle_exam_officer_active", args=[self.superadmin.id])
        )

        self.assertEqual(response.status_code, 404)
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.is_active)

    def test_toggle_requires_post(self):
        self.client.force_login(self.superadmin)

        response = self.client.get(
            reverse("toggle_exam_officer_active", args=[self.officer.id])
        )

        self.assertEqual(response.status_code, 405)
        self.officer.refresh_from_db()
        self.assertTrue(self.officer.is_active)

    def test_superadmin_can_reset_officer_password(self):
        self.client.force_login(self.superadmin)
        url = reverse("reset_exam_officer_password", args=[self.officer.id])

        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)

        response = self.client.post(url, {
            "new_password1": "ResetPass!234",
            "new_password2": "ResetPass!234",
        })

        self.assertRedirects(
            response, reverse("exam_officer_list"), fetch_redirect_response=False
        )
        self.officer.refresh_from_db()
        self.assertTrue(self.officer.check_password("ResetPass!234"))

    def test_officer_cannot_reset_another_officers_password(self):
        other = User.objects.create_user(
            username="_other_officer",
            password="OtherPass!234",
            is_staff=True,
        )
        self.client.force_login(self.officer)

        response = self.client.post(
            reverse("reset_exam_officer_password", args=[other.id]),
            {"new_password1": "Hijack!234", "new_password2": "Hijack!234"},
        )

        self.assertEqual(response.status_code, 403)
        other.refresh_from_db()
        self.assertTrue(other.check_password("OtherPass!234"))

    def test_officer_can_change_their_own_password(self):
        self.client.force_login(self.officer)

        response = self.client.post(reverse("password_change"), {
            "old_password": "OfficerPass!234",
            "new_password1": "ChangedPass!234",
            "new_password2": "ChangedPass!234",
        })

        self.assertRedirects(
            response,
            reverse("password_change_done"),
            fetch_redirect_response=False,
        )
        self.officer.refresh_from_db()
        self.assertTrue(self.officer.check_password("ChangedPass!234"))

    def test_officer_login_page_links_to_superadmin_login(self):
        response = self.client.get(reverse("exam_officer_login"))

        self.assertContains(response, reverse("superadmin_login"))
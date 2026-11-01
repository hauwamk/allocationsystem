import shutil
import tempfile
from datetime import date, time, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from allocations.models import Allocation, ExamSession
from courses.models import Course
from invigilators.models import Invigilator
from students.models import Student, Registration
from exams.models import Exam, Timetable
from exams.clash_service import find_clashes
from exams.views import PENDING_TIMETABLE_REPLACE_KEY
from venues.models import Venue


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
        self.timetable = Timetable.objects.create(name="2027 First Semester")

    def _exam(self, course, start=time(9, 0), duration=120, timetable=None):
        return Exam.objects.create(
            course=course, exam_date=date(2026, 12, 1), exam_time=start,
            duration=duration, timetable=timetable or self.timetable,
        )

    def test_detects_clash_when_two_registered_courses_share_a_slot(self):
        # Both exams on the same date and time — this student can't sit both.
        exam_a = self._exam(self.course_a)
        exam_b = self._exam(self.course_b)

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 1)
        self.assertEqual(clashes[0]["student"], self.student)
        self.assertEqual(clashes[0]["exam_a"], exam_a)
        self.assertEqual(clashes[0]["exam_b"], exam_b)

    def test_no_clash_when_exams_are_at_different_times(self):
        exam_a = self._exam(self.course_a)
        self._exam(self.course_b, start=time(14, 0))

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 0)

    def test_detects_clash_when_exams_only_partly_overlap(self):
        # 09:00-11:00 and 10:00-11:00 share an hour even though their
        # start times differ, so the student still cannot sit both.
        exam_a = self._exam(self.course_a, start=time(9, 0), duration=120)
        exam_b = self._exam(self.course_b, start=time(10, 0), duration=60)

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 1)
        self.assertEqual(clashes[0]["exam_b"], exam_b)

    def test_back_to_back_exams_do_not_clash(self):
        # One ends exactly when the other starts, so both can be sat.
        exam_a = self._exam(self.course_a, start=time(9, 0), duration=120)
        self._exam(self.course_b, start=time(11, 0), duration=60)

        self.assertEqual(find_clashes(exam_a), [])

    def test_a_draft_in_another_batch_does_not_clash(self):
        exam_a = self._exam(self.course_a)
        other_draft = Timetable.objects.create(name="Other Draft")
        self._exam(self.course_b, timetable=other_draft)

        self.assertEqual(find_clashes(exam_a), [])

    def test_a_published_exam_in_another_batch_does_clash(self):
        exam_a = self._exam(self.course_a)
        published = Timetable.objects.create(
            name="Already Published", status="PUBLISHED"
        )
        exam_b = self._exam(self.course_b, timetable=published)

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 1)
        self.assertEqual(clashes[0]["exam_b"], exam_b)

    def test_standalone_exam_is_checked_against_published_exams(self):
        exam_a = Exam.objects.create(
            course=self.course_a, exam_date=date(2026, 12, 1),
            exam_time=time(9, 0), duration=120,
        )
        published = Timetable.objects.create(
            name="Already Published", status="PUBLISHED"
        )
        exam_b = self._exam(self.course_b, timetable=published)

        clashes = find_clashes(exam_a)

        self.assertEqual(len(clashes), 1)
        self.assertEqual(clashes[0]["exam_a"], exam_a)
        self.assertEqual(clashes[0]["exam_b"], exam_b)


class TimetableUploadTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.timetable = Timetable.objects.create(name="2027 First Semester")
        self.course = Course.objects.create(
            course_code="CSC400", course_title="Project", department="CS",
            level="400", semester="First",
        )

    def _upload(self, csv_text, replace=False):
        upload = SimpleUploadedFile(
            "timetable.csv", csv_text.encode("utf-8"), content_type="text/csv"
        )
        data = {"csv_file": upload}
        if replace:
            data["replace_existing"] = "on"
        return self.client.post(
            reverse("timetable_upload_csv", args=[self.timetable.id]), data
        )

    def test_uploading_a_sheet_creates_exams(self):
        response = self._upload(
            "Course Code,Date,Time,Duration\nCSC400,2027-01-11,09:00,120\n"
        )

        self.assertRedirects(
            response, reverse("timetable_detail", args=[self.timetable.id])
        )
        self.assertEqual(self.timetable.exams.count(), 1)

    def test_uploading_the_same_sheet_twice_does_not_duplicate_exams(self):
        csv_text = "Course Code,Date,Time,Duration\nCSC400,2027-01-11,09:00,120\n"

        self._upload(csv_text)
        self._upload(csv_text)

        self.assertEqual(self.timetable.exams.count(), 1)

    def test_duplicate_rows_inside_one_file_are_imported_once(self):
        self._upload(
            "Course Code,Date,Time,Duration\n"
            "CSC400,2027-01-11,09:00,120\n"
            "CSC400,2027-01-11,09:00,120\n"
        )

        self.assertEqual(self.timetable.exams.count(), 1)

    def test_replace_existing_replaces_the_batch_after_confirmation(self):
        self._upload(
            "Course Code,Date,Time,Duration\nCSC400,2027-01-11,09:00,120\n"
        )
        self._upload(
            "Course Code,Date,Time,Duration\nCSC400,2027-01-12,14:00,90\n",
            replace=True,
        )

        # Uploading only stages the replacement; nothing is deleted yet.
        self.assertEqual(self.timetable.exams.count(), 1)
        self.assertEqual(self.timetable.exams.get().exam_date, date(2027, 1, 11))

        self.client.post(
            reverse("confirm_timetable_replace", args=[self.timetable.id]),
            {"action": "confirm"},
        )

        self.assertEqual(self.timetable.exams.count(), 1)
        exam = self.timetable.exams.get()
        self.assertEqual(exam.exam_date, date(2027, 1, 12))
        self.assertEqual(exam.exam_time, time(14, 0))


class TimetableFileUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.addCleanup(self.override.disable)

        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.timetable = Timetable.objects.create(name="2027 First Semester")

    def _png(self, name="timetable.png"):
        buffer = BytesIO()
        Image.new("RGB", (800, 400), "white").save(buffer, format="PNG")
        return SimpleUploadedFile(
            name, buffer.getvalue(), content_type="image/png"
        )

    def _pdf(self, pages=1, name="timetable.pdf"):
        buffer = BytesIO()
        first = Image.new("RGB", (600, 300), "white")
        extra = [Image.new("RGB", (600, 300), "white") for _ in range(pages - 1)]
        first.save(buffer, format="PDF", save_all=True, append_images=extra)
        return SimpleUploadedFile(
            name, buffer.getvalue(), content_type="application/pdf"
        )

    def _upload(self, upload):
        return self.client.post(
            reverse("timetable_upload_file", args=[self.timetable.id]),
            {"source_file": upload},
        )

    def test_uploading_an_image_stores_the_file(self):
        response = self._upload(self._png())

        self.assertRedirects(
            response, reverse("timetable_detail", args=[self.timetable.id])
        )
        self.timetable.refresh_from_db()
        self.assertTrue(self.timetable.source_file)
        self.assertEqual(self.timetable.source_file_name, "timetable.png")

    def test_uploading_a_pdf_stores_the_file(self):
        self._upload(self._pdf())

        self.timetable.refresh_from_db()
        self.assertTrue(self.timetable.source_file_name.endswith(".pdf"))

    def test_unsupported_file_type_is_rejected(self):
        response = self._upload(
            SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        )

        self.assertRedirects(
            response, reverse("timetable_detail", args=[self.timetable.id])
        )
        self.timetable.refresh_from_db()
        self.assertFalse(self.timetable.source_file)

    def test_a_corrupt_image_is_rejected(self):
        self._upload(
            SimpleUploadedFile("broken.png", b"not an image", content_type="image/png")
        )

        self.timetable.refresh_from_db()
        self.assertFalse(self.timetable.source_file)

    def test_a_pdf_with_too_many_pages_is_rejected(self):
        self._upload(self._pdf(pages=6))

        self.timetable.refresh_from_db()
        self.assertFalse(self.timetable.source_file)

    def test_replacing_the_file_deletes_the_old_one(self):
        self._upload(self._png(name="first.png"))
        self.timetable.refresh_from_db()
        old_path = self.timetable.source_file.path

        self._upload(self._png(name="second.png"))

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.source_file_name, "second.png")
        self.assertFalse(self.timetable.source_file.storage.exists(old_path))


class TimetableStatusGuardTests(TestCase):
    """A batch can only be edited while it is a draft, and it can be retired."""

    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.timetable = Timetable.objects.create(name="2027 First Semester")
        self.course = Course.objects.create(
            course_code="CSC400", course_title="Project", department="CS",
            level="400", semester="First",
        )

    def _upload(self, rows="CSC400,2027-01-11,09:00,120", timetable=None):
        upload = SimpleUploadedFile(
            "timetable.csv",
            f"Course Code,Date,Time,Duration\n{rows}\n".encode("utf-8"),
            content_type="text/csv",
        )
        return self.client.post(
            reverse("timetable_upload_csv", args=[(timetable or self.timetable).id]),
            {"csv_file": upload},
        )

    def _png(self):
        buffer = BytesIO()
        Image.new("RGB", (80, 40), "white").save(buffer, format="PNG")
        return SimpleUploadedFile(
            "timetable.png", buffer.getvalue(), content_type="image/png"
        )

    def _set_status(self, status):
        self.timetable.status = status
        self.timetable.save(update_fields=["status"])
        self.timetable.refresh_from_db()

    # -- course code matching -------------------------------------------

    def test_course_code_matches_ignoring_case(self):
        self._upload("csc400,2027-01-11,09:00,120")

        self.assertEqual(self.timetable.exams.count(), 1)
        self.assertEqual(self.timetable.exams.get().course, self.course)

    def test_ambiguous_course_codes_are_reported_and_nothing_is_imported(self):
        Course.objects.create(
            course_code="csc400", course_title="Duplicate", department="CS",
            level="400", semester="First",
        )

        self._upload("CSC400,2027-01-11,09:00,120")

        self.assertEqual(self.timetable.exams.count(), 0)

    # -- published batches are frozen -----------------------------------

    def test_published_batch_rejects_exam_upload(self):
        self._set_status("PUBLISHED")

        self._upload()

        self.assertEqual(self.timetable.exams.count(), 0)

    def test_archived_batch_rejects_exam_upload(self):
        self._set_status("ARCHIVED")

        self._upload()

        self.assertEqual(self.timetable.exams.count(), 0)

    def test_published_batch_rejects_file_replacement(self):
        self._set_status("PUBLISHED")

        self.client.post(
            reverse("timetable_upload_file", args=[self.timetable.id]),
            {"source_file": self._png()},
        )

        self.timetable.refresh_from_db()
        self.assertFalse(self.timetable.source_file)

    def test_published_batch_exam_cannot_be_edited(self):
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=self.timetable,
        )
        self._set_status("PUBLISHED")

        self.client.post(reverse("edit_exam", args=[exam.id]), {
            "course": self.course.id,
            "exam_date": "2027-02-01",
            "exam_time": "14:00",
            "duration": 90,
        })

        exam.refresh_from_db()
        self.assertEqual(exam.exam_date, date(2027, 1, 11))

    def test_published_batch_exam_cannot_be_deleted(self):
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=self.timetable,
        )
        self._set_status("PUBLISHED")

        self.client.post(reverse("delete_exam", args=[exam.id]))

        self.assertTrue(Exam.objects.filter(id=exam.id).exists())

    def test_standalone_exam_can_still_be_deleted(self):
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120,
        )

        self.client.post(reverse("delete_exam", args=[exam.id]))

        self.assertFalse(Exam.objects.filter(id=exam.id).exists())

    # -- status transitions ---------------------------------------------

    def test_publish_requires_a_draft(self):
        self._set_status("ARCHIVED")

        self.client.post(reverse("publish_timetable", args=[self.timetable.id]))

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "ARCHIVED")

    def test_unpublish_returns_a_published_batch_to_draft(self):
        self._set_status("PUBLISHED")

        self.client.post(reverse("unpublish_timetable", args=[self.timetable.id]))

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")

    def test_unpublish_is_refused_for_a_draft(self):
        self.client.post(reverse("unpublish_timetable", args=[self.timetable.id]))

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")

    def test_archive_then_restore(self):
        self.client.post(reverse("archive_timetable", args=[self.timetable.id]))
        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "ARCHIVED")

        self.client.post(reverse("restore_timetable", args=[self.timetable.id]))
        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")

    def test_restore_is_refused_for_a_draft(self):
        self.client.post(reverse("restore_timetable", args=[self.timetable.id]))

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")

    # -- delete ---------------------------------------------------------

    def test_delete_removes_the_batch_its_exams_and_its_seats(self):
        student = Student.objects.create(
            registration_number="CS/400/001", first_name="A", last_name="B",
            department="CS", level="400", gender="M",
        )
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=self.timetable,
        )
        venue = Venue.objects.create(venue_name="Hall", capacity=10)
        invigilator = Invigilator.objects.create(staff_id="INV1", full_name="Inv")
        session = ExamSession.objects.create(
            exam=exam, venue=venue, invigilator=invigilator
        )
        Allocation.objects.create(
            student=student, exam_session=session, seating_number=1
        )

        response = self.client.get(
            reverse("delete_timetable", args=[self.timetable.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["exam_count"], 1)
        self.assertEqual(response.context["session_count"], 1)
        self.assertEqual(response.context["seat_count"], 1)

        self.client.post(reverse("delete_timetable", args=[self.timetable.id]))

        self.assertFalse(Timetable.objects.filter(id=self.timetable.id).exists())
        self.assertFalse(Exam.objects.filter(id=exam.id).exists())
        self.assertFalse(ExamSession.objects.filter(id=session.id).exists())
        self.assertFalse(Allocation.objects.filter(student=student).exists())
        self.assertTrue(Student.objects.filter(id=student.id).exists())


class TimetableReplacePreviewTests(TestCase):
    """Replace stages the change and shows it before deleting anything."""

    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.timetable = Timetable.objects.create(name="2027 First Semester")
        self.csc = Course.objects.create(
            course_code="CSC400", course_title="Project", department="CS",
            level="400", semester="First",
        )
        self.mth = Course.objects.create(
            course_code="MTH1203", course_title="Maths", department="CS",
            level="100", semester="First",
        )
        self.exam = Exam.objects.create(
            course=self.csc, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120, timetable=self.timetable,
        )

    def _upload(self, rows, replace=True):
        upload = SimpleUploadedFile(
            "timetable.csv",
            f"Course Code,Date,Time,Duration\n{rows}".encode("utf-8"),
            content_type="text/csv",
        )
        data = {"csv_file": upload}
        if replace:
            data["replace_existing"] = "on"
        return self.client.post(
            reverse("timetable_upload_csv", args=[self.timetable.id]), data
        )

    def _confirm(self, action="confirm"):
        return self.client.post(
            reverse("confirm_timetable_replace", args=[self.timetable.id]),
            {"action": action},
        )

    def test_unreadable_file_leaves_the_batch_untouched(self):
        self._upload("NOPE999,not-a-date,99:99,abc\n")

        self.assertEqual(self.timetable.exams.count(), 1)
        self.assertTrue(Exam.objects.filter(id=self.exam.id).exists())
        self.assertNotIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)

    def test_replace_changes_nothing_until_confirmed(self):
        self._upload("MTH1203,2027-01-12,14:00,90\n")

        self.assertTrue(Exam.objects.filter(id=self.exam.id).exists())
        self.assertEqual(self.timetable.exams.count(), 1)

        response = self.client.get(
            reverse("timetable_detail", args=[self.timetable.id])
        )
        preview = response.context["replace_preview"]
        self.assertEqual([row["course"] for row in preview["to_add"]], [self.mth])
        self.assertEqual([exam.id for exam in preview["to_remove"]], [self.exam.id])

        self._confirm()

        self.assertFalse(Exam.objects.filter(id=self.exam.id).exists())
        exam = self.timetable.exams.get()
        self.assertEqual(exam.course, self.mth)
        self.assertEqual(exam.exam_date, date(2027, 1, 12))
        self.assertEqual(exam.exam_time, time(14, 0))
        self.assertNotIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)

    def test_cancelling_keeps_the_existing_exams(self):
        self._upload("MTH1203,2027-01-12,14:00,90\n")

        self._confirm("cancel")

        self.assertTrue(Exam.objects.filter(id=self.exam.id).exists())
        self.assertFalse(Exam.objects.filter(course=self.mth).exists())
        self.assertNotIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)

    def test_preview_lists_rows_that_will_be_skipped(self):
        self._upload(
            "MTH1203,2027-01-12,14:00,90\n"
            "NOPE999,2027-01-13,09:00,120\n"
        )

        pending = self.client.session[PENDING_TIMETABLE_REPLACE_KEY]
        self.assertEqual(len(pending["errors"]), 1)

        self._confirm()

        self.assertFalse(Exam.objects.filter(id=self.exam.id).exists())
        self.assertEqual(self.timetable.exams.count(), 1)
        self.assertEqual(self.timetable.exams.get().course, self.mth)

    def test_confirm_is_refused_when_the_batch_is_no_longer_draft(self):
        self._upload("MTH1203,2027-01-12,14:00,90\n")
        self.timetable.status = "PUBLISHED"
        self.timetable.save(update_fields=["status"])

        self._confirm()

        self.assertTrue(Exam.objects.filter(id=self.exam.id).exists())
        self.assertFalse(Exam.objects.filter(course=self.mth).exists())
        self.assertNotIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)

    def test_expired_preview_is_refused(self):
        self._upload("MTH1203,2027-01-12,14:00,90\n")

        session = self.client.session
        pending = session[PENDING_TIMETABLE_REPLACE_KEY]
        pending["created_at"] = (timezone.now() - timedelta(hours=2)).isoformat()
        session[PENDING_TIMETABLE_REPLACE_KEY] = pending
        session.save()

        self._confirm()

        self.assertTrue(Exam.objects.filter(id=self.exam.id).exists())
        self.assertFalse(Exam.objects.filter(course=self.mth).exists())

    def test_confirm_removes_seating_of_removed_exams(self):
        student = Student.objects.create(
            registration_number="CS/400/002", first_name="A", last_name="B",
            department="CS", level="400", gender="M",
        )
        venue = Venue.objects.create(venue_name="Hall", capacity=10)
        invigilator = Invigilator.objects.create(staff_id="INV2", full_name="Inv")
        exam_session = ExamSession.objects.create(
            exam=self.exam, venue=venue, invigilator=invigilator
        )
        Allocation.objects.create(
            student=student, exam_session=exam_session, seating_number=1
        )

        self._upload("MTH1203,2027-01-12,14:00,90\n")
        response = self.client.get(
            reverse("timetable_detail", args=[self.timetable.id])
        )
        self.assertEqual(response.context["replace_preview"]["seat_count"], 1)

        self._confirm()

        self.assertFalse(Allocation.objects.filter(student=student).exists())

    def test_a_new_upload_discards_the_pending_preview(self):
        self._upload("MTH1203,2027-01-12,14:00,90\n")
        self.assertIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)

        self._upload("MTH1203,2027-01-12,14:00,90\n", replace=False)

        self.assertNotIn(PENDING_TIMETABLE_REPLACE_KEY, self.client.session)


class TimetablePublishTests(TestCase):
    """Publishing refuses what students cannot actually sit."""

    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.timetable = Timetable.objects.create(name="2027 First Semester")
        self.course_a = Course.objects.create(
            course_code="CSA300", course_title="Course A", department="CS",
            level="300", semester="First",
        )
        self.course_b = Course.objects.create(
            course_code="CSB300", course_title="Course B", department="CS",
            level="300", semester="First",
        )
        self.student = Student.objects.create(
            registration_number="CS/300/001", first_name="Test", last_name="Student",
            department="CS", level="300", gender="M",
        )
        Registration.objects.create(student=self.student, course=self.course_a)
        Registration.objects.create(student=self.student, course=self.course_b)
        self.venue = Venue.objects.create(venue_name="Hall A", capacity=50)
        self.invigilator = Invigilator.objects.create(
            staff_id="STF100", full_name="Invigilator"
        )

    def _exam(self, course, start=time(9, 0), duration=120, timetable=None):
        return Exam.objects.create(
            course=course, exam_date=date(2027, 1, 11), exam_time=start,
            duration=duration, timetable=timetable or self.timetable,
        )

    def _seat(self, exam, students=None):
        session = ExamSession.objects.create(
            exam=exam, venue=self.venue, invigilator=self.invigilator
        )
        for number, student in enumerate(students or [self.student], start=1):
            Allocation.objects.create(
                student=student, exam_session=session, seating_number=number
            )

    def _publish(self):
        return self.client.post(
            reverse("publish_timetable", args=[self.timetable.id]), follow=True
        )

    def test_empty_batch_cannot_be_published(self):
        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")
        self.assertContains(response, "has no exams yet")

    def test_exam_with_registered_students_needs_a_venue(self):
        self._exam(self.course_a)

        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")
        self.assertContains(response, "no venue has been assigned")

    def test_exam_without_registrations_does_not_need_seating(self):
        empty_course = Course.objects.create(
            course_code="CSC999", course_title="Nobody Registered",
            department="CS", level="300", semester="First",
        )
        self._exam(empty_course)

        self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "PUBLISHED")

    def test_a_fully_seated_batch_publishes(self):
        self._seat(self._exam(self.course_a))

        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "PUBLISHED")
        self.assertContains(response, "is now published")

    def test_partially_seated_exam_is_refused(self):
        second_student = Student.objects.create(
            registration_number="CS/300/002", first_name="Second", last_name="Student",
            department="CS", level="300", gender="F",
        )
        Registration.objects.create(student=second_student, course=self.course_a)
        exam = self._exam(self.course_a)
        self._seat(exam, students=[self.student])

        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")
        self.assertContains(response, "only 1 of 2")

    def test_duration_overlap_between_batch_exams_blocks_publishing(self):
        self._seat(self._exam(self.course_a, start=time(9, 0), duration=120))
        self._seat(self._exam(self.course_b, start=time(10, 0), duration=60))

        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")
        self.assertContains(response, "overlaps")
        self.assertContains(response, "CSA300")
        self.assertContains(response, "CSB300")

    def test_clash_with_a_draft_in_another_batch_does_not_block_publishing(self):
        other_draft = Timetable.objects.create(name="Other Draft")
        self._seat(self._exam(self.course_a, start=time(9, 0), duration=120))
        self._exam(
            self.course_b, start=time(10, 0), duration=60, timetable=other_draft
        )

        self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "PUBLISHED")

    def test_clash_with_a_published_batch_blocks_publishing(self):
        published = Timetable.objects.create(
            name="Already Published", status="PUBLISHED"
        )
        self._seat(self._exam(self.course_a, start=time(9, 0), duration=120))
        self._exam(
            self.course_b, start=time(10, 0), duration=60, timetable=published
        )

        response = self._publish()

        self.timetable.refresh_from_db()
        self.assertEqual(self.timetable.status, "DRAFT")
        self.assertContains(response, "overlaps")


class ExamFormBatchTests(TestCase):
    """An exam's batch decides whether students can see it."""

    def setUp(self):
        User.objects.create_user(
            username="officer", password="testpass123", is_staff=True
        )
        self.client.login(username="officer", password="testpass123")
        self.course = Course.objects.create(
            course_code="CSC400", course_title="Project", department="CS",
            level="400", semester="First",
        )
        self.draft = Timetable.objects.create(name="2027 First Semester")
        self.published = Timetable.objects.create(
            name="2026 Second Semester", status="PUBLISHED"
        )

    def _post_add(self, timetable_id=""):
        return self.client.post(reverse("add_exam"), {
            "course": self.course.id,
            "timetable": timetable_id,
            "exam_date": "2027-01-11",
            "exam_time": "09:00",
            "duration": 120,
        })

    def test_adding_an_exam_can_put_it_in_a_draft_batch(self):
        self._post_add(self.draft.id)

        self.assertEqual(Exam.objects.get().timetable, self.draft)

    def test_adding_an_exam_without_a_batch_is_allowed(self):
        self._post_add()

        self.assertIsNone(Exam.objects.get().timetable)

    def test_an_exam_cannot_be_added_to_a_published_batch(self):
        response = self._post_add(self.published.id)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Exam.objects.exists())

    def test_editing_an_exam_can_move_it_into_a_draft_batch(self):
        exam = Exam.objects.create(
            course=self.course, exam_date=date(2027, 1, 11),
            exam_time=time(9, 0), duration=120,
        )

        self.client.post(reverse("edit_exam", args=[exam.id]), {
            "course": self.course.id,
            "timetable": self.draft.id,
            "exam_date": "2027-01-11",
            "exam_time": "09:00",
            "duration": 120,
        })

        exam.refresh_from_db()
        self.assertEqual(exam.timetable, self.draft)

    def test_the_course_picker_is_flagged_for_the_search_box(self):
        response = self.client.get(reverse("add_exam"))

        self.assertContains(response, 'data-searchable="true"')
        self.assertContains(response, 'data-search-placeholder="Type to filter courses"')


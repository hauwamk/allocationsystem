
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Course


class ImportCoursesTests(TestCase):
    def setUp(self):
        # import_courses is protected by @staff_required
        self.staff_user = User.objects.create_user(username="officer", password="testpass123", is_staff=True)
        self.client.login(username="officer", password="testpass123")

    def test_import_creates_course_with_all_fields(self):
        csv_content = (
            "Course Code,Course Title,Department,Level,Semester\n"
            "CSC201,Data Structures,CS,200,First\n"
        )
        upload = SimpleUploadedFile(
            "courses.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("import_courses"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        course = Course.objects.filter(course_code="CSC201").first()
        self.assertIsNotNone(course)
        self.assertEqual(course.course_title, "Data Structures")
        self.assertEqual(course.department, "CS")
        self.assertEqual(course.level, "200")
        self.assertEqual(course.semester, "First")

    def test_import_does_not_overwrite_existing_course(self):
        Course.objects.create(
            course_code="CSC201", course_title="Old Title",
            department="CS", level="200", semester="First",
        )
        csv_content = (
            "Course Code,Course Title,Department,Level,Semester\n"
            "CSC201,New Title,SE,300,Second\n"
        )
        upload = SimpleUploadedFile("courses.csv", csv_content.encode("utf-8"), content_type="text/csv")
        self.client.post(reverse("import_courses"), {"csv_file": upload}, follow=True)

        course = Course.objects.get(course_code="CSC201")
        self.assertEqual(course.course_title, "Old Title")

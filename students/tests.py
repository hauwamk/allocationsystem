from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Student


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
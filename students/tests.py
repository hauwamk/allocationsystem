from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Student


class ImportStudentsTests(TestCase):
    def test_import_accepts_common_header_names(self):
        csv_content = (
            "Registration Number,First Name,Last Name,Level,Gender,Email\n"
            "ABC123,Jane,Doe,300,F,jane@example.com\n"
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
        self.assertTrue(Student.objects.filter(registration_number="ABC123").exists())

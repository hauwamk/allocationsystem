from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Invigilator


class ImportInvigilatorsTests(TestCase):
    def setUp(self):
        # import_invigilators is protected by @staff_required
        self.staff_user = User.objects.create_user(username="officer", password="testpass123", is_staff=True)
        self.client.login(username="officer", password="testpass123")

    def test_import_creates_invigilator_with_working_login(self):
        csv_content = (
            "Staff ID,Full Name,Phone Number\n"
            "STF001,Jane Doe,08012345678\n"
        )
        upload = SimpleUploadedFile(
            "invigilators.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("import_invigilators"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        invigilator = Invigilator.objects.filter(staff_id="STF001").first()
        self.assertIsNotNone(invigilator)
        self.assertEqual(invigilator.full_name, "Jane Doe")

        # The whole point of auto-login-creation: confirm the login
        # actually works with staff_id as both username and password.
        self.assertIsNotNone(invigilator.user)
        self.assertTrue(invigilator.user.check_password("STF001"))

# Create your tests here.

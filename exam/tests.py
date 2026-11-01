from datetime import date, time
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from courses.models import Course
from exams.models import Exam, Timetable
from invigilators.models import Invigilator
from students.models import Registration, Student

from .imports import XLSX_CONTENT_TYPE


def _xlsx_upload(filename, headers, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return SimpleUploadedFile(filename, buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)


class StaffTestCase(TestCase):
    def setUp(self):
        User.objects.create_user(username="officer", password="testpass123", is_staff=True)
        self.client.login(username="officer", password="testpass123")


class ExcelImportTests(StaffTestCase):
    def test_students_xlsx_import_creates_login(self):
        upload = _xlsx_upload(
            "students.xlsx",
            [
                "Registration Number",
                "First Name",
                "Last Name",
                "Department",
                "Level",
                "Gender",
                "Email",
            ],
            [["CST/22/SWE/00042", "Amina", "Yusuf", "SWE", 300, "F", "amina@example.com"]],
        )

        response = self.client.post(
            reverse("import_students"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(registration_number="CST/22/SWE/00042")
        self.assertEqual(student.level, "300")
        self.assertEqual(student.department, "SWE")
        self.assertEqual(student.user.username, "CST/22/SWE/00042")
        self.assertTrue(student.user.check_password("CST/22/SWE/00042"))

    def test_courses_xlsx_import_creates_course(self):
        upload = _xlsx_upload(
            "courses.xlsx",
            ["Course Code", "Course Title", "Department", "Level", "Semester"],
            [["SWE301", "Software Engineering", "SWE", 300, "First"]],
        )

        response = self.client.post(
            reverse("import_courses"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        course = Course.objects.get(course_code="SWE301")
        self.assertEqual(course.course_title, "Software Engineering")
        self.assertEqual(course.department, "SWE")
        self.assertEqual(course.level, "300")
        self.assertEqual(course.semester, "First")

    def test_invigilators_xlsx_import_creates_login(self):
        upload = _xlsx_upload(
            "invigilators.xlsx",
            ["Staff ID", "Full Name", "Phone Number"],
            [["STF777", "Dr. Aisha Bello", "08030000000"]],
        )

        response = self.client.post(
            reverse("import_invigilators"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        invigilator = Invigilator.objects.get(staff_id="STF777")
        self.assertEqual(invigilator.full_name, "Dr. Aisha Bello")
        self.assertEqual(invigilator.phone_number, "08030000000")
        self.assertTrue(invigilator.user.check_password("STF777"))

    def test_registrations_xlsx_import_registers_students(self):
        student = Student.objects.create(
            registration_number="CST/22/SWE/00001",
            first_name="Amina",
            last_name="Yusuf",
            department="SWE",
            level="200",
            gender="F",
        )
        course = Course.objects.create(
            course_code="SWE201",
            course_title="Data Structures",
            department="SWE",
            level="200",
            semester="First",
        )
        upload = _xlsx_upload(
            "registrations.xlsx",
            ["Reg No", "Full Name"],
            [["CST/22/SWE/00001", "Amina Yusuf"]],
        )

        response = self.client.post(
            reverse("import_registrations"),
            {"course": course.id, "csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Registration.objects.filter(student=student, course=course).exists()
        )

    def test_timetable_xlsx_import_parses_excel_date_and_time(self):
        course = Course.objects.create(
            course_code="SWE301",
            course_title="Software Engineering",
            department="SWE",
            level="300",
            semester="First",
        )
        timetable = Timetable.objects.create(name="2026 First Semester")
        upload = _xlsx_upload(
            "timetable.xlsx",
            ["Course Code", "Date", "Time", "Duration"],
            [["SWE301", date(2026, 12, 7), time(9, 0), 120]],
        )

        response = self.client.post(
            reverse("timetable_upload_csv", args=[timetable.id]),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        exam = Exam.objects.get(course=course, timetable=timetable)
        self.assertEqual(exam.exam_date, date(2026, 12, 7))
        self.assertEqual(exam.exam_time, time(9, 0))
        self.assertEqual(exam.duration, 120)

    def test_legacy_xls_file_is_rejected(self):
        upload = SimpleUploadedFile(
            "students.xls", b"legacy-content", content_type="application/vnd.ms-excel"
        )

        response = self.client.post(
            reverse("import_students"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Legacy .xls files are not supported")
        self.assertEqual(Student.objects.count(), 0)

    def test_corrupt_xlsx_reports_read_error(self):
        upload = SimpleUploadedFile(
            "students.xlsx", b"not-a-real-workbook", content_type=XLSX_CONTENT_TYPE
        )

        response = self.client.post(
            reverse("import_students"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Excel file could not be read")
        self.assertEqual(Student.objects.count(), 0)


class ImportTemplateDownloadTests(StaffTestCase):
    templates = [
        (
            "students",
            "students-import-template.xlsx",
            "Students",
            [
                "Registration Number",
                "First Name",
                "Last Name",
                "Department",
                "Level",
                "Gender",
                "Email",
            ],
        ),
        (
            "courses",
            "courses-import-template.xlsx",
            "Courses",
            ["Course Code", "Course Title", "Department", "Level", "Semester"],
        ),
        (
            "invigilators",
            "invigilators-import-template.xlsx",
            "Invigilators",
            ["Staff ID", "Full Name", "Phone Number"],
        ),
        (
            "registrations",
            "course-registrations-import-template.xlsx",
            "Registrations",
            ["Reg No", "Full Name"],
        ),
        (
            "timetable",
            "timetable-exams-import-template.xlsx",
            "Exams",
            ["Course Code", "Date", "Time", "Duration"],
        ),
    ]

    def test_each_template_downloads_with_expected_headers(self):
        for kind, filename, sheet_title, headers in self.templates:
            with self.subTest(kind=kind):
                response = self.client.get(
                    reverse("download_import_template", args=[kind])
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], XLSX_CONTENT_TYPE)
                self.assertIn(f'filename="{filename}"', response["Content-Disposition"])

                workbook = load_workbook(BytesIO(response.content), read_only=True)
                try:
                    self.assertEqual(workbook.sheetnames, [sheet_title, "Instructions"])
                    worksheet = workbook.worksheets[0]
                    actual_headers = [
                        cell.value
                        for cell in next(
                            worksheet.iter_rows(min_row=1, max_row=1)
                        )
                    ]
                    self.assertEqual(actual_headers, headers)
                    self.assertEqual(worksheet.max_row, 1)
                finally:
                    workbook.close()

    def test_downloaded_students_template_can_be_imported(self):
        template = self.client.get(reverse("download_import_template", args=["students"]))
        workbook = load_workbook(BytesIO(template.content))
        worksheet = workbook.worksheets[0]
        worksheet.append(
            ["CST/22/SWE/00043", "Fatima", "Musa", "SWE", "200", "F", "fatima@example.com"]
        )
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()

        upload = SimpleUploadedFile(
            "filled-template.xlsx", buffer.getvalue(), content_type=XLSX_CONTENT_TYPE
        )
        response = self.client.post(
            reverse("import_students"), {"csv_file": upload}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Student.objects.filter(registration_number="CST/22/SWE/00043").exists()
        )

    def test_template_download_requires_staff_login(self):
        self.client.logout()

        response = self.client.get(reverse("download_import_template", args=["students"]))

        self.assertEqual(response.status_code, 302)

    def test_unknown_template_returns_404(self):
        response = self.client.get(
            reverse("download_import_template", args=["unknown"])
        )

        self.assertEqual(response.status_code, 404)

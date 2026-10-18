from datetime import date, time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from students.models import Student, Registration
from courses.models import Course
from venues.models import Venue
from invigilators.models import Invigilator
from exams.models import Exam, Timetable
from allocations.services import allocate_exam


class Command(BaseCommand):
    help = "Seeds initial demo data (officers, venues, courses, students, and an allocated timetable)"

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        # 1. Superadmin & Exam Officer
        admin_user, _ = User.objects.get_or_create(username="admin", defaults={"email": "admin@buk.edu.ng", "is_staff": True, "is_superuser": True})
        admin_user.set_password("admin123")
        admin_user.save()

        officer_user, _ = User.objects.get_or_create(username="officer1", defaults={"email": "officer@buk.edu.ng", "is_staff": True, "is_superuser": False})
        officer_user.set_password("officer123")
        officer_user.save()

        # 2. Venues
        v1, _ = Venue.objects.get_or_create(venue_name="Lecture Theatre A", defaults={"capacity": 50})
        v2, _ = Venue.objects.get_or_create(venue_name="Software Engineering Lab", defaults={"capacity": 30})
        v3, _ = Venue.objects.get_or_create(venue_name="Cybersecurity Lab", defaults={"capacity": 25})
        v4, _ = Venue.objects.get_or_create(venue_name="Main Examination Hall", defaults={"capacity": 100})

        # 3. Invigilators
        inv_data = [
            ("STAFF/0101", "Dr. Haruna Musa", "08031234567"),
            ("STAFF/0102", "Malama Hadiza Umar", "08037654321"),
            ("STAFF/0103", "Dr. Bashir Lawal", "08029876543"),
        ]
        for staff_id, name, phone in inv_data:
            user, _ = User.objects.get_or_create(username=staff_id)
            user.set_password(staff_id)
            user.save()
            Invigilator.objects.get_or_create(staff_id=staff_id, defaults={"user": user, "full_name": name, "phone_number": phone})

        # 4. Courses
        course_data = [
            ("COM201", "Data Structures and Algorithms", "COM", "200", "First"),
            ("SWE201", "Software Requirements Analysis", "SWE", "200", "First"),
            ("IFT201", "Internet & Web Technologies", "IFT", "200", "First"),
            ("CBS201", "Network Security & Protocols", "CBS", "200", "First"),
            ("MTH201", "Linear Algebra & Matrices", "ALL", "200", "First"),
        ]
        courses = {}
        for code, title, dept, lvl, sem in course_data:
            c, _ = Course.objects.get_or_create(course_code=code, defaults={"course_title": title, "department": dept, "level": lvl, "semester": sem})
            courses[code] = c

        # 5. Students & Course Registrations
        students_info = [
            ("CST/22/COM/001", "Amina", "Ibrahim", "COM", "200", "F"),
            ("CST/22/COM/002", "Usman", "Bello", "COM", "200", "M"),
            ("CST/22/COM/003", "Aliyu", "Garba", "COM", "200", "M"),
            ("CST/22/COM/004", "Maryam", "Sani", "COM", "200", "F"),
            ("CST/22/SWE/001", "Fatima", "Umar", "SWE", "200", "F"),
            ("CST/22/SWE/002", "Kabir", "Ahmed", "SWE", "200", "M"),
            ("CST/22/SWE/003", "Zainab", "Mustapha", "SWE", "200", "F"),
            ("CST/22/IFT/001", "Nasir", "Idris", "IFT", "200", "M"),
            ("CST/22/CBS/001", "Hauwa", "Abubakar", "CBS", "200", "F"),
            ("CST/22/CBS/002", "Suleiman", "Dahir", "CBS", "200", "M"),
        ]
        for reg_no, first, last, dept, lvl, gender in students_info:
            u, _ = User.objects.get_or_create(username=reg_no)
            u.set_password(reg_no)
            u.save()
            student, _ = Student.objects.get_or_create(
                registration_number=reg_no,
                defaults={"user": u, "first_name": first, "last_name": last, "department": dept, "level": lvl, "gender": gender}
            )
            # Register for their dept course and shared MTH201
            dept_course_code = f"{dept}201"
            if dept_course_code in courses:
                Registration.objects.get_or_create(student=student, course=courses[dept_course_code])
            Registration.objects.get_or_create(student=student, course=courses["MTH201"])

        # 6. Timetable & Exams
        tt, _ = Timetable.objects.get_or_create(name="2026 First Semester Examination Batch", defaults={"status": "PUBLISHED"})
        tt.status = "PUBLISHED"
        tt.save()

        exam_dates = [
            ("MTH201", date(2026, 11, 16), time(9, 0), 180),
            ("COM201", date(2026, 11, 17), time(9, 0), 120),
            ("SWE201", date(2026, 11, 18), time(9, 0), 120),
        ]
        for ccode, edate, etime, dur in exam_dates:
            exam, _ = Exam.objects.get_or_create(
                course=courses[ccode],
                exam_date=edate,
                exam_time=etime,
                defaults={"duration": dur, "timetable": tt}
            )
            try:
                allocate_exam(exam)
            except Exception as e:
                self.stdout.write(f"Allocation for {ccode}: {e}")

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("Superadmin: admin / admin123"))
        self.stdout.write(self.style.SUCCESS("Exam Officer: officer1 / officer123"))
        self.stdout.write(self.style.SUCCESS("Sample Student: CST/22/COM/001 / CST/22/COM/001"))
        self.stdout.write(self.style.SUCCESS("Sample Invigilator: STAFF/0101 / STAFF/0101"))

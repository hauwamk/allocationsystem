from django.db.models import Count, Q
from django.shortcuts import render
from accounts.decorators import staff_required
from students.models import Student
from courses.models import Course
from venues.models import Venue
from exams.models import Exam
from invigilators.models import Invigilator
from allocations.models import Allocation


@staff_required
def dashboard(request):
    total_students = Student.objects.count()
    total_courses = Course.objects.count()
    total_venues = Venue.objects.count()
    total_exams = Exam.objects.count()
    total_invigilators = Invigilator.objects.count()
    total_allocations = Allocation.objects.count()
    department_counts = Student.objects.values('department').annotate(count=Count('id')).order_by('department')
    context = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_venues': total_venues,
        'total_exams': total_exams,
        'total_invigilators': total_invigilators,
        'total_allocations': total_allocations,
        'department_counts': department_counts
    }
    return render(request, 'dashboard/dashboard.html', context)


@staff_required
def department_list(request):
    """
    Read-only overview of the fixed departments. Department isn't its
    own database table — this just loops over the choices already
    defined on Student, with a student/course count for each.
    """
    departments = []
    for code, name in Student.DEPARTMENT_CHOICES:
        departments.append({
            "code": code,
            "name": name,
            "student_count": Student.objects.filter(department=code).count(),
            "course_count": Course.objects.filter(department=code).count(),
        })
    return render(request, "dashboard/department_list.html", {"departments": departments})


@staff_required
def department_detail(request, code):
    """
    One department's students and courses. `code` is the short code
    (e.g. 'SWE'), not a database ID, since Department isn't a real model.
    Courses tagged "ALL" (shared across every department) are included
    here too, since students in this department do take them.
    """
    department_name = dict(Student.DEPARTMENT_CHOICES).get(code, code)
    students = Student.objects.filter(department=code)
    courses = Course.objects.filter(Q(department=code) | Q(department="ALL"))
    return render(request, "dashboard/department_detail.html", {
        "department_code": code,
        "department_name": department_name,
        "students": students,
        "courses": courses,
    })
from django.contrib import messages
from django.shortcuts import render, redirect

from accounts.decorators import staff_required
from students.models import Student, Registration
from courses.models import Course


@staff_required
def bulk_register(request):
    """
    Step 1 (no filters yet): show a form to pick department + level + semester.
    Step 2 (filters present, GET): show matching courses and matching
        students, all pre-checked, so the officer can uncheck exceptions.
    Step 3 (POST): create a Registration for every checked student x
        checked course combination. get_or_create means running this
        again later (e.g. after adding late students) is safe — no
        duplicates.
    """
    department = request.GET.get("department") or request.POST.get("department")
    level = request.GET.get("level") or request.POST.get("level")
    semester = request.GET.get("semester") or request.POST.get("semester")

    if request.method == "POST" and department and level and semester:
        student_ids = request.POST.getlist("students")
        course_ids = request.POST.getlist("courses")
        students = Student.objects.filter(id__in=student_ids)
        courses = Course.objects.filter(id__in=course_ids)

        created = 0
        for student in students:
            for course in courses:
                _, was_created = Registration.objects.get_or_create(student=student, course=course)
                if was_created:
                    created += 1

        messages.success(
            request,
            f"Registered {students.count()} student(s) for {courses.count()} course(s) "
            f"— {created} new registration(s) created.",
        )
        return redirect("students_list")

    if department and level and semester:
        courses = Course.objects.filter(department=department, level=level, semester=semester)
        students = Student.objects.filter(department=department, level=level)
        return render(request, "students/bulk_register_confirm.html", {
            "department": department,
            "level": level,
            "semester": semester,
            "courses": courses,
            "students": students,
        })

    return render(request, "students/bulk_register_select.html", {
        "departments": Student.DEPARTMENT_CHOICES,
        "levels": Student.LEVEL_CHOICES,
        "semesters": Course.SEMESTER_CHOICES,
    })
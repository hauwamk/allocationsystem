from django.db.models import Q
from django.shortcuts import render

from accounts.decorators import staff_required
from exam.departments import department_codes
from exam.imports import (
    ImportFileError,
    get_field as _get_field,
    read_tabular_upload,
)
from exam.pagination import paginate
from .models import Course
from .forms import CourseForm, CourseImportForm
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from students.models import Registration

@staff_required
def courses_list(request):
    courses = Course.objects.all().order_by("course_code")
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    semester = request.GET.get("semester", "").strip()

    if query:
        courses = courses.filter(
            Q(course_code__icontains=query) | Q(course_title__icontains=query)
        )
    if department:
        courses = courses.filter(department__in=department_codes(department))
    if level:
        courses = courses.filter(level=level)
    if semester:
        courses = courses.filter(semester=semester)

    page_obj = paginate(request, courses)
    context = {
        "courses": page_obj,
        "page_obj": page_obj,
        "departments": Course.DEPARTMENT_CHOICES,
        "levels": Course.LEVEL_CHOICES,
        "semesters": Course.SEMESTER_CHOICES,
    }
    return render(request, "courses/course_list.html", context)

@staff_required
def edit_course(request, id):
    course = get_object_or_404(Course, id=id)

    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)

        if form.is_valid():
            form.save()
            messages.success(request, "Course updated successfully.")
            return redirect("course_list")

    else:
        form = CourseForm(instance=course)

    return render(request, "courses/edit_course.html", {"form": form})

@staff_required
def delete_course(request, id):
    course = get_object_or_404(Course, id=id)

    if request.method == "POST":
        course.delete()
        messages.success(request, "Course deleted successfully.")
        return redirect("course_list")

    return render(request, "courses/delete_course.html", {"course": course})

@staff_required
def add_course(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Course added successfully.")
            return redirect("course_list")
    else:
        form = CourseForm()

    return render(request, "courses/add_course.html", {"form": form})


@staff_required
def import_courses(request):
    """
    CSV or Excel columns expected: Course Code, Course Title, Department,
    Level, Semester.
    Department must be one of: CS, SE, IT, CY.
    Level must be one of: 100, 200, 300, 400.
    Semester must be exactly: First or Second.
    Existing courses (matched by course_code) are left untouched, not overwritten.
    """
    if request.method == "POST":
        form = CourseImportForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                data = read_tabular_upload(request.FILES["csv_file"])
            except ImportFileError as exc:
                messages.error(request, str(exc))
                data = None

            imported = 0
            skipped = 0

            if data is not None and not data.headers:
                messages.error(request, "The uploaded file does not contain any headers.")
            elif data is not None:
                for row in data.rows:
                    course_code = _get_field(row, "course_code", "course code")
                    if not course_code:
                        continue

                    course_title = _get_field(row, "course_title", "course title")
                    department = _get_field(row, "department")
                    level = _get_field(row, "level")
                    semester = _get_field(row, "semester")

                    _, created = Course.objects.get_or_create(
                        course_code=course_code,
                        defaults={
                            "course_title": course_title,
                            "department": department,
                            "level": level,
                            "semester": semester,
                        },
                    )

                    if created:
                        imported += 1
                    else:
                        skipped += 1

                messages.success(
                    request,
                    f"Import completed! Imported: {imported}, Skipped: {skipped}",
                )
                return redirect("course_list")

    else:
        form = CourseImportForm()

    return render(request, "courses/import_courses.html", {"form": form})

@staff_required
def course_students(request, id):
    """Shows every student registered for one course."""
    course = get_object_or_404(Course, id=id)

    # All registrations for this course, with the student loaded in one query,
    # sorted by registration number.
    registrations = (
        Registration.objects.filter(course=course)
        .select_related("student")
        .order_by("student__registration_number")
    )

    return render(
        request,
        "courses/course_students.html",
        {"course": course, "registrations": registrations},
    )
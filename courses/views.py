import csv
import re
from io import TextIOWrapper

from django.shortcuts import render

from accounts.decorators import staff_required
from .models import Course
from .forms import CourseForm, CourseImportForm
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages


def _normalize_header(header):
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _normalize_row(row):
    normalized = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[_normalize_header(key)] = value or ""
    return normalized


def _get_field(row, *possible_names):
    normalized_row = _normalize_row(row)
    for name in possible_names:
        value = normalized_row.get(_normalize_header(name), "")
        if value:
            return value.strip()
    return ""


@staff_required
def courses_list(request):
    courses = Course.objects.all()
    context = {'courses': courses}
    return render(request, 'courses/course_list.html', context)

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
    CSV columns expected: Course Code, Course Title, Department, Level, Semester.
    Department must be one of: CS, SE, IT, CY.
    Level must be one of: 100, 200, 300, 400.
    Semester must be exactly: First or Second.
    Existing courses (matched by course_code) are left untouched, not overwritten.
    """
    if request.method == "POST":
        form = CourseImportForm(request.POST, request.FILES)

        if form.is_valid():
            csv_file = request.FILES["csv_file"]
            file = TextIOWrapper(csv_file.file, encoding="utf-8")
            reader = csv.DictReader(file)

            imported = 0
            skipped = 0

            if not reader.fieldnames:
                messages.error(request, "The uploaded file does not contain any headers.")
            else:
                for row in reader:
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
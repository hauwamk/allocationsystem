import csv
import re
from io import TextIOWrapper

from django.contrib import messages
from django.shortcuts import render

from accounts.decorators import staff_required
from .forms import StudentEditForm, StudentImportForm, RegisterCourseForm
from .models import Student, Registration

from django.shortcuts import get_object_or_404, redirect


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
def students_list(request):
    students = Student.objects.all()
    context = {'students': students}
    return render(request, 'students/student_list.html', context)

@staff_required
def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)

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
                    registration_number = _get_field(row, "registration_number", "registration number")
                    if not registration_number:
                        continue

                    first_name = _get_field(row, "first_name", "first name")
                    last_name = _get_field(row, "last_name", "last name")
                    level = _get_field(row, "level")
                    department = _get_field(row, "department")
                    gender = _get_field(row, "gender")
                    email = _get_field(row, "email")

                    _, created = Student.objects.get_or_create(
                        registration_number=registration_number,
                        defaults={
                            "first_name": first_name,
                            "last_name": last_name,
                            "level": level,
                            "department": department,
                            "gender": gender,
                            "email": email,
                        },
                    )

                    if created:
                        from django.contrib.auth.models import User
                        student = Student.objects.get(registration_number=registration_number)
                        user, _ = User.objects.get_or_create(username=registration_number)
                        user.set_password(registration_number)
                        user.save()
                        student.user = user
                        student.save()

                    if created:
                        imported += 1
                    else:
                        skipped += 1

                messages.success(
                    request,
                    f"Import completed! Imported: {imported}, Skipped: {skipped}",
                )

    else:
        form = StudentImportForm()

    return render(
        request,
        "students/importstudentslist.html",
        {"form": form},
    )

@staff_required
def delete_student(request, id):
    student = get_object_or_404(Student, id=id)

    if request.method == "POST":
        student.delete()
        messages.success(request, "Student deleted successfully.")
        return redirect("students_list")

    return render(request, "students/delete_student.html", {"student": student})

@staff_required
def edit_student(request, id):
    student = get_object_or_404(Student, id=id)

    if request.method == "POST":
        form = StudentEditForm(request.POST, instance=student)

        if form.is_valid():
            form.save()
            messages.success(request, "Student updated successfully.")
            return redirect("students_list")

    else:
        form = StudentEditForm(instance=student)

    return render(request, "students/edit_student.html", {"form": form})

@staff_required
def add_student(request):
    if request.method == "POST":
        form = StudentEditForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            from django.contrib.auth.models import User
            user, _ = User.objects.get_or_create(username=student.registration_number)
            user.set_password(student.registration_number)
            user.save()
            student.user = user
            student.save()
            messages.success(request, "Student added successfully.")
            return redirect("students_list")
    else:
        form = StudentEditForm()

    return render(request, "students/add_student.html", {"form": form})

@staff_required
def register_courses(request, id):
    student = get_object_or_404(Student, id=id)
    current_course_ids = Registration.objects.filter(student=student).values_list("course_id", flat=True)

    if request.method == "POST":
        form = RegisterCourseForm(request.POST)
        if form.is_valid():
            selected_courses = form.cleaned_data["courses"]
            Registration.objects.filter(student=student).exclude(course__in=selected_courses).delete()
            for course in selected_courses:
                Registration.objects.get_or_create(student=student, course=course)
            messages.success(request, f"Updated course registrations for {student.registration_number}.")
            return redirect("students_list")
    else:
        form = RegisterCourseForm(initial={"courses": current_course_ids})

    return render(request, "students/register_courses.html", {"form": form, "student": student})
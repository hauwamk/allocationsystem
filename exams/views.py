import csv
import re
from datetime import datetime
from io import TextIOWrapper

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.decorators import staff_required
from .models import Exam, Timetable
from .forms import ExamForm, TimetableForm, TimetableUploadForm
from allocations.services import allocate_exam, allocate_semester


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


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_time(value):
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (ValueError, TypeError):
        return None


def find_clashes(exam):
    """
    Finds students registered for BOTH this exam's course and a different
    course whose exam is scheduled at the exact same date and time.
    """
    from students.models import Registration

    students_in_this_exam = Registration.objects.filter(
        course=exam.course
    ).select_related("student")

    clashes = []
    for registration in students_in_this_exam:
        student = registration.student
        other_registrations = Registration.objects.filter(
            student=student
        ).exclude(course=exam.course)

        for other_registration in other_registrations:
            conflicting_exam = Exam.objects.filter(
                course=other_registration.course,
                exam_date=exam.exam_date,
                exam_time=exam.exam_time,
            ).exclude(id=exam.id).first()

            if conflicting_exam:
                clashes.append({
                    "student": student,
                    "exam_a": exam,
                    "exam_b": conflicting_exam,
                })
    return clashes


def _warn_about_clashes(request, exam):
    clashes = find_clashes(exam)
    for clash in clashes:
        messages.warning(
            request,
            f"Schedule clash: {clash['student'].registration_number} is "
            f"registered for both {clash['exam_a'].course.course_code} and "
            f"{clash['exam_b'].course.course_code}, which are scheduled at "
            f"the same date and time."
        )
    return clashes


# ---------------------------------------------------------------------
# Single-exam CRUD (unchanged behavior)
# ---------------------------------------------------------------------

@staff_required
def exam_list(request):
    exams = Exam.objects.all()
    return render(request, "exams/exam_list.html", {"exams": exams})


@staff_required
def edit_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if request.method == "POST":
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam updated successfully.")
            _warn_about_clashes(request, exam)
            return redirect("exam_list")
    else:
        form = ExamForm(instance=exam)
    return render(request, "exams/edit_exam.html", {"form": form})


@staff_required
def delete_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if request.method == "POST":
        exam.delete()
        messages.success(request, "Exam deleted successfully.")
        return redirect("exam_list")
    return render(request, "exams/delete_exam.html", {"exam": exam})


@staff_required
def add_exam(request):
    if request.method == "POST":
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save()
            messages.success(request, "Exam added successfully.")
            _warn_about_clashes(request, exam)
            return redirect("exam_list")
    else:
        form = ExamForm()
    return render(request, "exams/add_exam.html", {"form": form})


@staff_required
def allocate_exam_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    try:
        sessions = allocate_exam(exam)
        messages.success(
            request,
            f"{exam.course.course_code} allocated across {len(sessions)} venue(s).",
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("exam_list")


@staff_required
def allocate_all_exams_view(request):
    results = allocate_semester(Exam.objects.all())
    for exam, sessions in results["succeeded"]:
        messages.success(
            request,
            f"{exam.course.course_code} allocated across {len(sessions)} venue(s).",
        )
    for exam, error in results["failed"]:
        messages.error(request, f"{exam.course.course_code}: {error}")
    if not results["succeeded"] and not results["failed"]:
        messages.info(request, "No exams to allocate.")
    return redirect("exam_list")


# ---------------------------------------------------------------------
# Timetable: create draft -> upload exams -> review clashes -> publish
# ---------------------------------------------------------------------

@staff_required
def timetable_list(request):
    timetables = Timetable.objects.all().order_by("-created_at")
    return render(request, "exams/timetable_list.html", {"timetables": timetables})


@staff_required
def timetable_create(request):
    if request.method == "POST":
        form = TimetableForm(request.POST)
        if form.is_valid():
            timetable = form.save()
            messages.success(request, f"Created draft timetable '{timetable.name}'. Now upload its exams.")
            return redirect("timetable_detail", timetable_id=timetable.id)
    else:
        form = TimetableForm()
    return render(request, "exams/timetable_form.html", {"form": form})


@staff_required
def timetable_detail(request, timetable_id):
    timetable = get_object_or_404(Timetable, id=timetable_id)
    exams = timetable.exams.select_related("course").order_by("exam_date", "exam_time")
    upload_form = TimetableUploadForm()
    return render(request, "exams/timetable_detail.html", {
        "timetable": timetable,
        "exams": exams,
        "upload_form": upload_form,
    })


@staff_required
def timetable_upload_csv(request, timetable_id):
    """
    CSV columns expected: Course Code, Date (YYYY-MM-DD), Time (HH:MM,
    24-hour), Duration (minutes).
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    form = TimetableUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Please choose a CSV file.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    from courses.models import Course

    csv_file = request.FILES["csv_file"]
    file = TextIOWrapper(csv_file.file, encoding="utf-8")
    reader = csv.DictReader(file)

    imported = 0
    errors = []

    if not reader.fieldnames:
        messages.error(request, "The uploaded file does not contain any headers.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    for row_number, row in enumerate(reader, start=2):
        course_code = _get_field(row, "course_code", "course code")
        date_str = _get_field(row, "date", "exam_date")
        time_str = _get_field(row, "time", "exam_time")
        duration_str = _get_field(row, "duration")

        if not course_code:
            continue

        course = Course.objects.filter(course_code=course_code).first()
        if course is None:
            errors.append(f"Row {row_number}: no course found with code '{course_code}'.")
            continue

        exam_date = _parse_date(date_str)
        if exam_date is None:
            errors.append(f"Row {row_number}: could not read date '{date_str}' (expected YYYY-MM-DD).")
            continue

        exam_time = _parse_time(time_str)
        if exam_time is None:
            errors.append(f"Row {row_number}: could not read time '{time_str}' (expected HH:MM, 24-hour).")
            continue

        try:
            duration = int(duration_str)
        except (ValueError, TypeError):
            errors.append(f"Row {row_number}: could not read duration '{duration_str}' as a number.")
            continue

        Exam.objects.create(
            course=course, exam_date=exam_date, exam_time=exam_time,
            duration=duration, timetable=timetable,
        )
        imported += 1

    messages.success(request, f"Imported {imported} exam(s) into '{timetable.name}'.")
    for error in errors:
        messages.error(request, error)

    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def publish_timetable(request, timetable_id):
    """
    Blocks publishing if any clash is found across the timetable's exams.
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    all_clashes = []
    for exam in timetable.exams.all():
        all_clashes.extend(find_clashes(exam))

    if all_clashes:
        messages.error(
            request,
            f"Cannot publish — {len(all_clashes)} schedule clash(es) found. Fix these before publishing:"
        )
        seen = set()
        for clash in all_clashes:
            key = tuple(sorted([clash["exam_a"].id, clash["exam_b"].id])) + (clash["student"].id,)
            if key in seen:
                continue
            seen.add(key)
            messages.warning(
                request,
                f"{clash['student'].registration_number}: "
                f"{clash['exam_a'].course.course_code} clashes with "
                f"{clash['exam_b'].course.course_code}"
            )
        return redirect("timetable_detail", timetable_id=timetable.id)

    timetable.status = "PUBLISHED"
    timetable.save()
    messages.success(request, f"'{timetable.name}' is now published — students can see it.")
    return redirect("timetable_detail", timetable_id=timetable.id)
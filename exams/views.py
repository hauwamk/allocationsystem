from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from accounts.decorators import staff_required
from courses.models import Course
from exam.departments import department_codes
from exam.imports import (
    ImportFileError,
    ROW_NUMBER_KEY,
    get_field as _get_field,
    read_tabular_upload,
)
from exam.pagination import paginate
from students.models import Registration
from .clash_service import find_clashes, find_timetable_clashes
from .models import Exam, Timetable
from .forms import ExamForm, TimetableFileForm, TimetableForm, TimetableUploadForm
from allocations.models import Allocation, ExamSession
from allocations.services import allocate_exam, allocate_semester


def _parse_date(value):
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def _parse_time(value):
    for date_format in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, date_format).time()
        except (ValueError, TypeError):
            continue
    return None


PENDING_TIMETABLE_REPLACE_KEY = "pending_timetable_replace"
PENDING_TIMETABLE_REPLACE_MAX_AGE = timedelta(hours=1)


def _pending_timetable_replace(request, timetable):
    """The replacement waiting for this batch, if it is still fresh."""
    pending = request.session.get(PENDING_TIMETABLE_REPLACE_KEY)
    if not pending or pending.get("timetable_id") != timetable.id:
        return None

    try:
        created_at = datetime.fromisoformat(pending.get("created_at", ""))
    except (TypeError, ValueError):
        created_at = None

    if created_at is None or timezone.now() - created_at > PENDING_TIMETABLE_REPLACE_MAX_AGE:
        request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)
        return None
    return pending


def _warn_about_clashes(request, exam):
    clashes = find_clashes(exam)
    for clash in clashes:
        messages.warning(
            request,
            f"Schedule clash: {clash['student'].registration_number} is "
            f"registered for both {clash['exam_a'].course.course_code} and "
            f"{clash['exam_b'].course.course_code}, whose exams overlap on "
            f"{clash['exam_a'].exam_date}."
        )
    return clashes


def _ensure_draft(request, timetable):
    """A batch can only be changed while it is a draft. Returns True if it is."""
    if timetable.status == "DRAFT":
        return True

    action = (
        "Restore it to draft"
        if timetable.status == "ARCHIVED"
        else "Unpublish it"
    )
    messages.error(
        request,
        f"'{timetable.name}' is {timetable.get_status_display().lower()}. "
        f"{action} before making changes.",
    )
    return False


def _exam_batch_is_locked(exam):
    """True when the exam belongs to a batch that is no longer a draft."""
    return exam.timetable_id is not None and exam.timetable.status != "DRAFT"


def _warn_exam_is_locked(request, exam):
    messages.error(
        request,
        f"{exam.course.course_code} belongs to '{exam.timetable.name}', which is "
        f"{exam.timetable.get_status_display().lower()}. Unpublish that timetable "
        "before changing its exams.",
    )


# ---------------------------------------------------------------------
# Single-exam CRUD (unchanged behavior)
# ---------------------------------------------------------------------

@staff_required
def exam_list(request):
    exams = (
        Exam.objects.select_related("course", "timetable")
        .annotate(
            session_count=Count("examsession", distinct=True),
            seat_count=Count("examsession__allocation", distinct=True),
        )
        .order_by("exam_date", "exam_time", "course__course_code")
    )
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    exam_date = _parse_date(request.GET.get("exam_date", "").strip())
    batch = request.GET.get("batch", "").strip()

    if query:
        exams = exams.filter(
            Q(course__course_code__icontains=query)
            | Q(course__course_title__icontains=query)
        )
    if department:
        exams = exams.filter(course__department__in=department_codes(department))
    if level:
        exams = exams.filter(course__level=level)
    if exam_date:
        exams = exams.filter(exam_date=exam_date)
    if batch == "standalone":
        exams = exams.filter(timetable__isnull=True)
    elif batch == "batch":
        exams = exams.filter(timetable__isnull=False)

    page_obj = paginate(request, exams)
    context = {
        "exams": page_obj,
        "page_obj": page_obj,
        "departments": Course.DEPARTMENT_CHOICES,
        "levels": Course.LEVEL_CHOICES,
    }
    return render(request, "exams/exam_list.html", context)


@staff_required
def edit_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if _exam_batch_is_locked(exam):
        _warn_exam_is_locked(request, exam)
        return redirect("exam_list")

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
    if _exam_batch_is_locked(exam):
        _warn_exam_is_locked(request, exam)
        return redirect("exam_list")

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
@require_POST
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
@require_POST
def clear_exam_allocation_view(request, exam_id):
    """Removes every seat and venue session belonging to one exam."""
    exam = get_object_or_404(Exam, id=exam_id)
    sessions = ExamSession.objects.filter(exam=exam)
    venue_count = sessions.count()
    seat_count = Allocation.objects.filter(exam_session__exam=exam).count()
    sessions.delete()

    if venue_count:
        messages.success(
            request,
            f"Seating cleared for {exam.course.course_code}: {seat_count} seat(s) "
            f"across {venue_count} venue(s) removed.",
        )
    else:
        messages.info(request, f"{exam.course.course_code} had no seating to clear.")
    return redirect("exam_list")


@staff_required
@require_POST
def allocate_all_exams_view(request):
    exams = list(
        Exam.objects.filter(timetable__status="DRAFT").select_related("course")
    )
    if not exams:
        messages.info(
            request,
            "No exams to allocate. Add exams to a draft timetable batch first.",
        )
        return redirect("exam_list")

    results = allocate_semester(exams)
    for exam, sessions in results["succeeded"]:
        messages.success(
            request,
            f"{exam.course.course_code} allocated across {len(sessions)} venue(s).",
        )
    for exam, error in results["failed"]:
        messages.error(request, f"{exam.course.course_code}: {error}")
    return redirect("exam_list")


# ---------------------------------------------------------------------
# Timetable: create draft -> upload exams -> review clashes -> publish
# ---------------------------------------------------------------------

@staff_required
def timetable_list(request):
    timetables = Timetable.objects.all().order_by("-created_at")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if query:
        timetables = timetables.filter(name__icontains=query)
    if status:
        timetables = timetables.filter(status=status)

    page_obj = paginate(request, timetables)
    context = {
        "timetables": page_obj,
        "page_obj": page_obj,
        "statuses": Timetable.STATUS_CHOICES,
    }
    return render(request, "exams/timetable_list.html", context)


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
    total_exams = exams.count()
    query = request.GET.get("q", "").strip()

    if query:
        exams = exams.filter(
            Q(course__course_code__icontains=query)
            | Q(course__course_title__icontains=query)
        )

    page_obj = paginate(request, exams)
    upload_form = TimetableUploadForm()
    file_form = TimetableFileForm()

    replace_preview = None
    pending = _pending_timetable_replace(request, timetable)
    if pending and timetable.status == "DRAFT":
        remove_ids = pending.get("remove_ids", [])
        to_remove = list(
            Exam.objects.filter(id__in=remove_ids)
            .select_related("course")
            .order_by("exam_date", "exam_time")
        )
        add_rows = pending.get("add", [])
        courses = {
            course.id: course
            for course in Course.objects.filter(id__in=[row[0] for row in add_rows])
        }
        to_add = []
        for course_id, date_str, time_str, duration in add_rows:
            course = courses.get(course_id)
            exam_date = _parse_date(date_str)
            exam_time = _parse_time(time_str)
            if course is None or exam_date is None or exam_time is None:
                continue
            to_add.append({
                "course": course,
                "exam_date": exam_date,
                "exam_time": exam_time,
                "duration": duration,
            })

        replace_preview = {
            "filename": pending.get("filename", ""),
            "to_remove": to_remove,
            "to_add": to_add,
            "errors": pending.get("errors", []),
            "seat_count": Allocation.objects.filter(
                exam_session__exam_id__in=remove_ids
            ).count(),
        }

    return render(request, "exams/timetable_detail.html", {
        "timetable": timetable,
        "exams": page_obj,
        "page_obj": page_obj,
        "total_exams": total_exams,
        "upload_form": upload_form,
        "file_form": file_form,
        "replace_preview": replace_preview,
    })


@staff_required
def timetable_upload_file(request, timetable_id):
    """
    Stores the official timetable document itself. Students download this
    file (converted to JPG or PNG) from their own Official Timetables page.
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if not _ensure_draft(request, timetable):
        return redirect("timetable_detail", timetable_id=timetable.id)

    form = TimetableFileForm(request.POST, request.FILES)
    if not form.is_valid():
        errors = "; ".join(
            error for field_errors in form.errors.values() for error in field_errors
        )
        messages.error(request, f"The timetable file was not uploaded: {errors}")
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.source_file:
        timetable.source_file.delete(save=False)
    timetable.source_file = form.cleaned_data["source_file"]
    timetable.save(update_fields=["source_file"])

    messages.success(
        request, f"Uploaded the timetable file for '{timetable.name}'."
    )
    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def timetable_upload_csv(request, timetable_id):
    """
    CSV or Excel columns expected: Course Code, Date (YYYY-MM-DD), Time
    (HH:MM, 24-hour), Duration (minutes).

    Rows that would duplicate an exam already in the batch (same course,
    date and time) are skipped, so re-uploading a corrected sheet does not
    silently create a second copy of every exam. Officers who want a clean
    slate can tick "replace existing": that never deletes from the upload
    itself, it stages the change until the officer confirms it.
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if not _ensure_draft(request, timetable):
        return redirect("timetable_detail", timetable_id=timetable.id)

    # A fresh upload always replaces any older preview waiting in this session.
    request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)

    form = TimetableUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        field_errors = form.errors.get("csv_file")
        messages.error(
            request,
            field_errors[0] if field_errors else "Please choose a CSV or Excel file.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    try:
        data = read_tabular_upload(request.FILES["csv_file"])
    except ImportFileError as exc:
        messages.error(request, str(exc))
        return redirect("timetable_detail", timetable_id=timetable.id)

    errors = []
    parsed_rows = []

    if not data.headers:
        messages.error(request, "The uploaded file does not contain any headers.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    for row in data.rows:
        row_number = row.get(ROW_NUMBER_KEY, "?")
        course_code = _get_field(row, "course_code", "course code")
        date_str = _get_field(row, "date", "exam_date")
        time_str = _get_field(row, "time", "exam_time")
        duration_str = _get_field(row, "duration")

        if not course_code:
            continue

        # Match regardless of case: officers often type CSC400 for csc400,
        # and the catalogue contains a mix of both.
        matches = list(Course.objects.filter(course_code__iexact=course_code))
        if not matches:
            errors.append(f"Row {row_number}: no course found with code '{course_code}'.")
            continue
        if len(matches) > 1:
            codes = ", ".join(sorted(course.course_code for course in matches))
            errors.append(
                f"Row {row_number}: '{course_code}' matches more than one course "
                f"({codes}). Fix the duplicate codes in Courses first."
            )
            continue
        course = matches[0]

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

        parsed_rows.append((course, exam_date, exam_time, duration))

    if form.cleaned_data["replace_existing"]:
        if not parsed_rows:
            # A wrong column or date format must never wipe the batch.
            messages.error(
                request,
                f"No row in that file could be read, so the exams in "
                f"'{timetable.name}' were left unchanged. Fix the rows below "
                "and upload again.",
            )
            for error in errors:
                messages.error(request, error)
            return redirect("timetable_detail", timetable_id=timetable.id)

        # Replacement removes exams with their venue sessions and seats, so
        # hold the exact add/remove sets until the officer confirms.
        seen_keys = set()
        add_rows = []
        for course, exam_date, exam_time, duration in parsed_rows:
            key = (course.id, exam_date, exam_time)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            add_rows.append([
                course.id, exam_date.isoformat(), exam_time.isoformat(), duration,
            ])

        request.session[PENDING_TIMETABLE_REPLACE_KEY] = {
            "timetable_id": timetable.id,
            "filename": request.FILES["csv_file"].name,
            "remove_ids": list(timetable.exams.values_list("id", flat=True)),
            "add": add_rows,
            "errors": errors,
            "created_at": timezone.now().isoformat(),
        }
        messages.info(
            request,
            "Nothing has been changed yet. Review the replacement below, "
            "then confirm or cancel.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    existing_keys = {
        (exam.course_id, exam.exam_date, exam.exam_time)
        for exam in timetable.exams.all()
    }

    imported = 0
    duplicates = 0
    seen_keys = set()
    for course, exam_date, exam_time, duration in parsed_rows:
        key = (course.id, exam_date, exam_time)
        if key in existing_keys or key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        Exam.objects.create(
            course=course, exam_date=exam_date, exam_time=exam_time,
            duration=duration, timetable=timetable,
        )
        imported += 1

    summary = f"Imported {imported} exam(s) into '{timetable.name}'."
    if duplicates:
        summary += f" Skipped {duplicates} duplicate row(s)."
    messages.success(request, summary)
    for error in errors:
        messages.error(request, error)

    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def confirm_timetable_replace(request, timetable_id):
    """Applies the replacement shown on the review card, after re-checking safety."""
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    action = request.POST.get("action")
    if action == "cancel":
        request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)
        messages.info(
            request,
            f"Replacement cancelled. The exams in '{timetable.name}' were left unchanged.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    if action != "confirm":
        request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)
        messages.error(request, "Nothing was changed: the replacement was not confirmed.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    pending = _pending_timetable_replace(request, timetable)
    if pending is None:
        messages.error(
            request,
            "There is no replacement waiting for confirmation. Upload the file again.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.status != "DRAFT":
        request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)
        messages.error(
            request,
            f"'{timetable.name}' is {timetable.get_status_display().lower()}, so its "
            "exams can't be replaced. Nothing was changed.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    remove_ids = [int(exam_id) for exam_id in pending.get("remove_ids", [])]
    add_rows = pending.get("add", [])
    courses = {
        course.id: course
        for course in Course.objects.filter(id__in=[row[0] for row in add_rows])
    }

    with transaction.atomic():
        removed = timetable.exams.filter(id__in=remove_ids).count()
        timetable.exams.filter(id__in=remove_ids).delete()

        remaining_keys = {
            (exam.course_id, exam.exam_date, exam.exam_time)
            for exam in timetable.exams.all()
        }
        imported = 0
        skipped = 0
        for course_id, date_str, time_str, duration in add_rows:
            course = courses.get(course_id)
            exam_date = _parse_date(date_str)
            exam_time = _parse_time(time_str)
            if course is None or exam_date is None or exam_time is None:
                skipped += 1
                continue
            key = (course.id, exam_date, exam_time)
            if key in remaining_keys:
                skipped += 1
                continue
            remaining_keys.add(key)
            Exam.objects.create(
                course=course, exam_date=exam_date, exam_time=exam_time,
                duration=duration, timetable=timetable,
            )
            imported += 1

    request.session.pop(PENDING_TIMETABLE_REPLACE_KEY, None)

    summary = (
        f"Replaced the exams in '{timetable.name}': removed {removed}, "
        f"imported {imported}."
    )
    if skipped:
        summary += f" Skipped {skipped} row(s) that could not be imported."
    messages.success(request, summary)
    return redirect("timetable_detail", timetable_id=timetable.id)


def _seating_problems(timetable, exams):
    """
    Exams in the batch that registered students cannot actually sit: no
    venue assigned, or fewer seats than registered students. Exams with no
    registrations are skipped — there is nobody to seat.
    """
    registered = {
        row["course_id"]: row["total"]
        for row in Registration.objects.filter(
            course_id__in=[exam.course_id for exam in exams]
        ).values("course_id").annotate(total=Count("id"))
    }
    sessions = {
        row["exam_id"]: row["total"]
        for row in ExamSession.objects.filter(exam__timetable=timetable)
        .values("exam_id").annotate(total=Count("id"))
    }
    seats = {
        row["exam_session__exam_id"]: row["total"]
        for row in Allocation.objects.filter(exam_session__exam__timetable=timetable)
        .values("exam_session__exam_id").annotate(total=Count("id"))
    }

    problems = []
    for exam in exams:
        registered_count = registered.get(exam.course_id, 0)
        if not registered_count:
            continue
        seat_count = seats.get(exam.id, 0)
        if not sessions.get(exam.id, 0):
            problems.append((exam, "no venue has been assigned."))
        elif seat_count < registered_count:
            problems.append((
                exam,
                f"only {seat_count} of {registered_count} registered "
                "student(s) have a seat.",
            ))
    return problems


@staff_required
def publish_timetable(request, timetable_id):
    """
    Publishing makes the batch visible to students, so it refuses an empty
    batch, an exam whose registered students are not seated, and any pair
    of exams whose times overlap for a student.
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.status != "DRAFT":
        messages.error(
            request,
            f"Only a draft timetable can be published. '{timetable.name}' is "
            f"{timetable.get_status_display().lower()}.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    exams = list(timetable.exams.select_related("course"))
    if not exams:
        messages.error(
            request,
            f"'{timetable.name}' has no exams yet, so there is nothing to "
            "publish. Upload its exams first.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    seating_problems = _seating_problems(timetable, exams)
    if seating_problems:
        messages.error(
            request,
            f"Cannot publish — {len(seating_problems)} exam(s) cannot seat "
            "their registered students. Allocate seating, then publish again:",
        )
        for exam, reason in seating_problems:
            messages.warning(request, f"{exam.course.course_code}: {reason}")
        return redirect("timetable_detail", timetable_id=timetable.id)

    clashes = find_timetable_clashes(timetable)
    if clashes:
        messages.error(
            request,
            f"Cannot publish — {len(clashes)} schedule clash(es) found. "
            "Fix these before publishing:",
        )
        for clash in clashes:
            messages.warning(
                request,
                f"{clash['student'].registration_number}: "
                f"{clash['exam_a'].course.course_code} "
                f"({clash['exam_a'].exam_time:%H:%M}) overlaps "
                f"{clash['exam_b'].course.course_code} "
                f"({clash['exam_b'].exam_time:%H:%M}) on "
                f"{clash['exam_a'].exam_date}.",
            )
        return redirect("timetable_detail", timetable_id=timetable.id)

    timetable.status = "PUBLISHED"
    timetable.save(update_fields=["status"])
    messages.success(request, f"'{timetable.name}' is now published — students can see it.")
    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def unpublish_timetable(request, timetable_id):
    """Takes a published batch back to draft so it can be corrected."""
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.status != "PUBLISHED":
        messages.error(
            request,
            f"'{timetable.name}' is not published, so there is nothing to unpublish.",
        )
        return redirect("timetable_detail", timetable_id=timetable.id)

    timetable.status = "DRAFT"
    timetable.save(update_fields=["status"])
    messages.success(
        request,
        f"'{timetable.name}' is back in draft. Students can no longer see it "
        "until you publish it again.",
    )
    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def archive_timetable(request, timetable_id):
    """Retires an exam period. Archived batches are hidden from students."""
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.status == "ARCHIVED":
        messages.error(request, f"'{timetable.name}' is already archived.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    timetable.status = "ARCHIVED"
    timetable.save(update_fields=["status"])
    messages.success(request, f"'{timetable.name}' is archived and hidden from students.")
    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def restore_timetable(request, timetable_id):
    """Brings an archived batch back to draft for editing or re-publishing."""
    timetable = get_object_or_404(Timetable, id=timetable_id)

    if request.method != "POST":
        return redirect("timetable_detail", timetable_id=timetable.id)

    if timetable.status != "ARCHIVED":
        messages.error(request, f"'{timetable.name}' is not archived.")
        return redirect("timetable_detail", timetable_id=timetable.id)

    timetable.status = "DRAFT"
    timetable.save(update_fields=["status"])
    messages.success(
        request, f"'{timetable.name}' is back in draft. Publish it when it is ready."
    )
    return redirect("timetable_detail", timetable_id=timetable.id)


@staff_required
def delete_timetable(request, timetable_id):
    """
    Permanently deletes a batch with its exams and seating. Unlike archive,
    this cannot be undone, so it always asks for confirmation first.
    """
    timetable = get_object_or_404(Timetable, id=timetable_id)
    exam_count = timetable.exams.count()
    session_count = ExamSession.objects.filter(exam__timetable=timetable).count()
    seat_count = Allocation.objects.filter(
        exam_session__exam__timetable=timetable
    ).count()

    if request.method == "POST":
        name = timetable.name
        if timetable.source_file:
            timetable.source_file.delete(save=False)
        timetable.delete()
        messages.success(
            request,
            f"Deleted '{name}' with {exam_count} exam(s) and {seat_count} seat(s).",
        )
        return redirect("timetable_list")

    return render(request, "exams/timetable_delete.html", {
        "timetable": timetable,
        "exam_count": exam_count,
        "session_count": session_count,
        "seat_count": seat_count,
    })
import re
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from accounts.decorators import staff_required, superadmin_required
from accounts.forms import ExamOfficerCreationForm
from accounts.timetable_image import render_timetable_image
from exam.imports import build_import_template_response
from exam.pagination import paginate
from exam.timetable_files import TimetableFileError, render_timetable_file
from exams.models import Timetable
from students.models import Registration
from allocations.models import Allocation, ExamSession

# How long before an exam a student is allowed to see their venue/seat.
# One place to change this if the rule ever needs adjusting.
VENUE_REVEAL_HOURS_BEFORE_EXAM = 1


class StudentLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"


def _build_student_exam_rows(student):
    """
    Shared logic for the student dashboard AND the printable timetable,
    so both pages always agree on which exams to show, which are
    completed, and when the venue/seat becomes visible. Returns
    (registered_courses, exam_rows).
    """
    registered_courses = [
        r.course for r in Registration.objects.filter(student=student).select_related("course")
    ]

    allocations = Allocation.objects.filter(student=student).select_related(
        "exam_session__exam__course", "exam_session__venue", "exam_session__invigilator"
    )
    allocation_by_exam_id = {a.exam_session.exam_id: a for a in allocations}

    now = timezone.now()

    exam_rows = []
    for course in registered_courses:
        for exam in course.exam_set.all():
            if exam.timetable is None or exam.timetable.status != "PUBLISHED":
                continue

            allocation = allocation_by_exam_id.get(exam.id)

            exam_datetime = datetime.combine(exam.exam_date, exam.exam_time)
            if timezone.is_aware(now):
                exam_datetime = timezone.make_aware(exam_datetime)

            duration_mins = getattr(exam, "duration", 0) or 0
            is_completed = now >= (exam_datetime + timedelta(minutes=duration_mins))
            reveal_time = exam_datetime - timedelta(hours=VENUE_REVEAL_HOURS_BEFORE_EXAM)
            can_view_venue = allocation is not None and now >= reveal_time

            exam_rows.append({
                "exam": exam,
                "allocation": allocation,
                "can_view_venue": can_view_venue,
                "is_completed": is_completed,
            })
    exam_rows.sort(key=lambda r: r["exam"].exam_date)
    return registered_courses, exam_rows


@login_required
def student_dashboard(request):
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

    registered_courses, exam_rows = _build_student_exam_rows(student)

    total_courses = len(registered_courses)
    completed_count = sum(1 for r in exam_rows if r["is_completed"])
    remaining_count = len(exam_rows) - completed_count
    seat_allocation_available = any(r["can_view_venue"] for r in exam_rows)

    context = {
        "student": student,
        "exam_rows": exam_rows,
        "total_courses": total_courses,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
        "seat_allocation_available": seat_allocation_available,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def student_timetable_print(request):
    """
    Standalone, print-friendly page listing every exam the logged-in
    student is registered for — their personal timetable. Uses the same
    venue-reveal rule as the dashboard, via _build_student_exam_rows, so
    the two pages can never show conflicting information.
    """
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

    _, exam_rows = _build_student_exam_rows(student)

    return render(request, "accounts/student_timetable_print.html", {
        "student": student,
        "exam_rows": exam_rows,
    })


@login_required
def student_timetable_image(request, image_format):
    """
    Downloads the student's timetable as a PNG or JPEG, so it can be kept
    on a phone or shared without printing. Built from the same rows as the
    on-screen timetable, so the venue reveal rule applies here too.
    """
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

    image_format = image_format.lower()
    if image_format == "jpeg":
        image_format = "jpg"
    if image_format not in ("png", "jpg"):
        raise Http404("Unsupported image format.")

    _, exam_rows = _build_student_exam_rows(student)
    content = render_timetable_image(student, exam_rows, image_format)

    safe_registration = re.sub(
        r"[^A-Za-z0-9]+", "-", student.registration_number
    ).strip("-")
    filename = (
        f"timetable-{safe_registration or 'student'}-"
        f"{timezone.localdate():%Y-%m-%d}.{image_format}"
    )

    response = HttpResponse(
        content,
        content_type="image/png" if image_format == "png" else "image/jpeg",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def student_official_timetables(request):
    """
    Lists the published timetable documents exam officers have uploaded.
    Students open this page to download the official timetable as an image.
    """
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

    timetables = (
        Timetable.objects.filter(status="PUBLISHED")
        .exclude(source_file="")
        .order_by("-created_at")
    )
    return render(request, "accounts/student_official_timetables.html", {
        "student": student,
        "timetables": timetables,
    })


@login_required
def student_official_timetable_download(request, timetable_id, image_format):
    """Converts an officer-uploaded timetable document to a JPG or PNG."""
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

    timetable = get_object_or_404(
        Timetable, id=timetable_id, status="PUBLISHED"
    )
    if not timetable.source_file:
        raise Http404("This timetable has no document attached.")

    image_format = image_format.lower()
    if image_format == "jpeg":
        image_format = "jpg"
    if image_format not in ("png", "jpg"):
        raise Http404("Unsupported image format.")

    try:
        content = render_timetable_file(timetable.source_file, image_format)
    except TimetableFileError as exc:
        messages.error(request, str(exc))
        return redirect("student_official_timetables")

    filename = f"{slugify(timetable.name) or 'timetable'}.{image_format}"
    response = HttpResponse(
        content,
        content_type="image/png" if image_format == "png" else "image/jpeg",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class InvigilatorLoginView(auth_views.LoginView):
    template_name = "accounts/invigilator_login.html"

    def get_default_redirect_url(self):
        return reverse("invigilator_dashboard")


@login_required
def invigilator_dashboard(request):
    invigilator = getattr(request.user, "invigilator", None)
    if invigilator is None:
        return redirect("invigilators_list")

    sessions = ExamSession.objects.filter(invigilator=invigilator).select_related(
        "exam__course", "venue"
    ).order_by("exam__exam_date")

    now = timezone.now()
    session_rows = []
    for session in sessions:
        exam = session.exam
        exam_dt = datetime.combine(exam.exam_date, exam.exam_time)
        if timezone.is_aware(now):
            exam_dt = timezone.make_aware(exam_dt)
        duration_mins = getattr(exam, "duration", 0) or 0
        is_completed = now >= (exam_dt + timedelta(minutes=duration_mins))
        session_rows.append({
            "session": session,
            "is_completed": is_completed,
        })

    total_sessions = len(session_rows)
    completed_count = sum(1 for r in session_rows if r["is_completed"])
    remaining_count = total_sessions - completed_count

    context = {
        "invigilator": invigilator,
        "session_rows": session_rows,
        "total_sessions": total_sessions,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
    }
    return render(
        request,
        "accounts/invigilator_dashboard.html",
        context,
    )


@staff_required
def import_hub(request):
    return render(request, "import_hub.html")


@staff_required
def download_import_template(request, kind):
    try:
        return build_import_template_response(kind)
    except KeyError:
        raise Http404("Unknown import template.")


class ExamOfficerLoginView(auth_views.LoginView):
    """
    Login for Exam Officer / Admin accounts — anyone with is_staff=True.
    Superadmin accounts (is_superuser=True) also have is_staff=True by
    default, so they COULD log in through this same page — but now that
    there is a visibly separate Superadmin login page (below), we block
    superusers here and point them to that page instead, so Superadmin
    isn't sharing an entry point with regular Exam Officers.
    """
    template_name = "accounts/exam_officer_login.html"

    def get_default_redirect_url(self):
        return "/dashboard/"

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            form.add_error(None, "This login is for Exam Officer / Admin accounts only.")
            return self.form_invalid(form)
        if user.is_superuser:
            form.add_error(
                None,
                "Superadmin accounts have their own login page. Please use the Superadmin Login link instead.",
            )
            return self.form_invalid(form)
        return super().form_valid(form)


class SuperadminLoginView(auth_views.LoginView):
    """
    A visibly separate login page for Superadmin accounts
    (is_superuser=True). This checks the exact same User table as
    ExamOfficerLoginView — the only real difference is WHICH accounts
    are let through here, and that it has its own distinct URL and
    template, so Superadmin isn't sharing an entry point with regular
    Exam Officers.
    """
    template_name = "accounts/superadmin_login.html"

    def get_default_redirect_url(self):
        return "/dashboard/"

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_superuser:
            form.add_error(None, "This login is for Superadmin accounts only.")
            return self.form_invalid(form)
        return super().form_valid(form)


# ---------------------------------------------------------------------
# Superadmin-only: manage Exam Officer accounts
# ---------------------------------------------------------------------

@superadmin_required
def exam_officer_list(request):
    """
    Lists every Exam Officer account (is_staff=True, is_superuser=False)
    — Superadmin accounts themselves aren't shown here, since this page
    is specifically about the accounts a Superadmin creates and manages.
    """
    officers = User.objects.filter(is_staff=True, is_superuser=False).order_by("username")
    query = request.GET.get("q", "").strip()
    active = request.GET.get("active", "").strip()

    if query:
        officers = officers.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if active in ("1", "0"):
        officers = officers.filter(is_active=(active == "1"))

    page_obj = paginate(request, officers)
    return render(
        request,
        "accounts/exam_officer_list.html",
        {"officers": page_obj, "page_obj": page_obj},
    )


@superadmin_required
def create_exam_officer(request):
    """
    The whole point of this feature: a Superadmin creates a new Exam
    Officer account here, in the app, with a real chosen password —
    instead of every officer being created via 'createsuperuser' on the
    command line (which would make them full superusers, not officers).
    """
    if request.method == "POST":
        form = ExamOfficerCreationForm(request.POST)
        if form.is_valid():
            officer = form.save(commit=False)
            officer.is_staff = True
            officer.is_superuser = False
            officer.save()
            messages.success(request, f"Exam Officer account '{officer.username}' created.")
            return redirect("exam_officer_list")
    else:
        form = ExamOfficerCreationForm()

    return render(request, "accounts/create_exam_officer.html", {"form": form})
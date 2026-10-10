from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import staff_required, superadmin_required
from accounts.forms import ExamOfficerCreationForm
from students.models import Registration
from allocations.models import Allocation, ExamSession

# How long before an exam a student is allowed to see their venue/seat.
# One place to change this if the rule ever needs adjusting.
VENUE_REVEAL_HOURS_BEFORE_EXAM = 1


class StudentLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"


@login_required
def student_dashboard(request):
    student = getattr(request.user, "student", None)
    if student is None:
        return redirect("students_list")

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
            if exam.timetable is not None and exam.timetable.status != "PUBLISHED":
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


class ExamOfficerLoginView(auth_views.LoginView):
    """
    Login for Exam Officer / Admin accounts — anyone with is_staff=True.
    Superadmin accounts (is_superuser=True) also have is_staff=True by
    default, so they log in through this exact same page — the extra
    Superadmin-only pages below are what actually differ for them.
    """
    template_name = "accounts/exam_officer_login.html"

    def get_default_redirect_url(self):
        return "/dashboard/"

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            form.add_error(None, "This login is for Exam Officer / Admin accounts only.")
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
    return render(request, "accounts/exam_officer_list.html", {"officers": officers})


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
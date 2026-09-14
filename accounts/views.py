from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import staff_required
from students.models import Registration
from allocations.models import Allocation, ExamSession

VENUE_REVEAL_HOURS_BEFORE_EXAM = 1


class StudentLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"


@staff_required
def import_hub(request):
    return render(request, "import_hub.html")


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
    today = now.date()

    exam_rows = []
    for course in registered_courses:
        for exam in course.exam_set.all():
            allocation = allocation_by_exam_id.get(exam.id)

            exam_datetime = datetime.combine(exam.exam_date, exam.exam_time)
            if timezone.is_aware(now):
                exam_datetime = timezone.make_aware(exam_datetime)
            reveal_time = exam_datetime - timedelta(hours=VENUE_REVEAL_HOURS_BEFORE_EXAM)
            can_view_venue = allocation is not None and now >= reveal_time

            exam_rows.append({
                "exam": exam,
                "allocation": allocation,
                "can_view_venue": can_view_venue,
                "is_completed": exam.exam_date < today,
            })
    exam_rows.sort(key=lambda r: r["exam"].exam_date)

    # Stats for the dashboard cards
    total_courses = len(registered_courses)
    total_exams = len(exam_rows)
    completed_count = sum(1 for r in exam_rows if r["is_completed"])
    remaining_count = total_exams - completed_count
    # "Available" once at least one upcoming exam's seat/venue is currently revealed
    seat_allocation_available = any(
        r["can_view_venue"] and not r["is_completed"] for r in exam_rows
    )

    return render(request, "accounts/dashboard.html", {
        "student": student,
        "exam_rows": exam_rows,
        "total_courses": total_courses,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
        "seat_allocation_available": seat_allocation_available,
    })


class InvigilatorLoginView(auth_views.LoginView):
    template_name = "accounts/invigilator_login.html"

    def get_default_redirect_url(self):
        return reverse("invigilator_dashboard")


@login_required
def invigilator_dashboard(request):
    invigilator = getattr(request.user, "invigilator", None)
    if invigilator is None:
        return redirect("invigilators_list")

    today = timezone.now().date()

    sessions = ExamSession.objects.filter(invigilator=invigilator).select_related(
        "exam__course", "venue"
    ).order_by("exam__exam_date")

    session_rows = [
        {"session": s, "is_completed": s.exam.exam_date < today}
        for s in sessions
    ]

    total_sessions = len(session_rows)
    completed_count = sum(1 for r in session_rows if r["is_completed"])
    remaining_count = total_sessions - completed_count

    return render(request, "accounts/invigilator_dashboard.html", {
        "invigilator": invigilator,
        "session_rows": session_rows,
        "total_sessions": total_sessions,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
    })


class ExamOfficerLoginView(auth_views.LoginView):
    template_name = "accounts/exam_officer_login.html"

    def get_default_redirect_url(self):
        return "/dashboard/"

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            form.add_error(None, "This login is for Exam Officer / Admin accounts only.")
            return self.form_invalid(form)
        return super().form_valid(form)
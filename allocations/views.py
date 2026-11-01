from datetime import datetime

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import staff_required
from courses.models import Course
from exam.departments import department_codes
from exam.pagination import paginate
from .models import ExamSession, Allocation


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@staff_required
def session_list(request):
    sessions = ExamSession.objects.select_related(
        "exam", "exam__course", "venue", "invigilator"
    ).annotate(seated=Count("allocation")).order_by(
        "exam__exam_date",
        "exam__exam_time",
        "exam__course__course_code",
        "venue__venue_name",
    )
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    exam_date = _parse_date(request.GET.get("exam_date", "").strip())

    if query:
        sessions = sessions.filter(
            Q(exam__course__course_code__icontains=query)
            | Q(exam__course__course_title__icontains=query)
            | Q(venue__venue_name__icontains=query)
            | Q(invigilator__full_name__icontains=query)
            | Q(invigilator__staff_id__icontains=query)
        )
    if department:
        sessions = sessions.filter(
            exam__course__department__in=department_codes(department)
        )
    if level:
        sessions = sessions.filter(exam__course__level=level)
    if exam_date:
        sessions = sessions.filter(exam__exam_date=exam_date)

    page_obj = paginate(request, sessions)
    context = {
        "sessions": page_obj,
        "page_obj": page_obj,
        "departments": Course.DEPARTMENT_CHOICES,
        "levels": Course.LEVEL_CHOICES,
    }
    return render(request, "allocations/session_list.html", context)


@staff_required
def session_detail(request, session_id):
    session = get_object_or_404(
        ExamSession.objects.select_related("exam", "exam__course", "venue", "invigilator"),
        id=session_id,
    )
    allocations = (
        Allocation.objects.filter(exam_session=session)
        .select_related("student")
        .order_by("seating_number")
    )
    query = request.GET.get("q", "").strip()

    if query:
        allocations = allocations.filter(
            Q(student__registration_number__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
        )

    page_obj = paginate(request, allocations, per_page=50)
    return render(
        request,
        "allocations/session_detail.html",
        {"session": session, "allocations": page_obj, "page_obj": page_obj},
    )


@staff_required
@require_POST
def remove_allocation(request, allocation_id):
    """
    Removes one student's seat. The seat number is left empty rather than
    renumbering the chart, and the student stays registered for the course,
    so re-allocating the exam will seat them again.
    """
    allocation = get_object_or_404(
        Allocation.objects.select_related("exam_session", "student"),
        id=allocation_id,
        exam_session__isnull=False,
    )
    session_id = allocation.exam_session_id
    registration_number = allocation.student.registration_number
    seat = allocation.seating_number
    allocation.delete()
    messages.success(request, f"Removed {registration_number} from seat {seat}.")
    return redirect("session_detail", session_id=session_id)


@staff_required
def session_print(request, session_id):
    """
    A standalone, printer-friendly page (no site nav/header) listing
    every seated student for one exam session — meant to be printed and
    posted outside the exam hall or handed to the invigilator.
    """
    session = get_object_or_404(
        ExamSession.objects.select_related("exam", "exam__course", "venue", "invigilator"),
        id=session_id,
    )
    allocations = (
        Allocation.objects.filter(exam_session=session)
        .select_related("student")
        .order_by("seating_number")
    )
    return render(
        request,
        "allocations/session_print.html",
        {"session": session, "allocations": allocations},
    )
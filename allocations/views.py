from django.shortcuts import render, get_object_or_404
from accounts.decorators import staff_required
from .models import ExamSession, Allocation


@staff_required
def session_list(request):
    sessions = ExamSession.objects.select_related(
        "exam", "exam__course", "venue", "invigilator"
    ).all()
    return render(request, "allocations/session_list.html", {"sessions": sessions})


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
    return render(
        request,
        "allocations/session_detail.html",
        {"session": session, "allocations": allocations},
    )
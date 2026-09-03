from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.shortcuts import render, redirect
from django.urls import reverse

from accounts.decorators import staff_required
from students.models import Registration
from allocations.models import Allocation, ExamSession


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

    exam_rows = []
    for course in registered_courses:
        for exam in course.exam_set.all():
            exam_rows.append({
                "exam": exam,
                "allocation": allocation_by_exam_id.get(exam.id),
            })
    exam_rows.sort(key=lambda r: r["exam"].exam_date)

    return render(request, "accounts/dashboard.html", {"student": student, "exam_rows": exam_rows})


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

    return render(
        request,
        "accounts/invigilator_dashboard.html",
        {"invigilator": invigilator, "sessions": sessions},
    )


@staff_required
def import_hub(request):
    return render(request, "import_hub.html")


class ExamOfficerLoginView(auth_views.LoginView):
    """
    Login for Exam Officer / Admin accounts — anyone with is_staff=True
    (e.g. an account created with 'python manage.py createsuperuser').
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
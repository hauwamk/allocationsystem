from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.decorators import staff_required
from .models import Exam
from .forms import ExamForm
from allocations.services import allocate_exam, allocate_semester


@staff_required
def exam_list(request):
    exams = Exam.objects.all()
    context = {
        "exams": exams,
    }
    return render(request, "exams/exam_list.html", context)


@staff_required
def edit_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if request.method == "POST":
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam updated successfully.")
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
            form.save()
            messages.success(request, "Exam added successfully.")
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
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Exam
from .forms import ExamForm

def exam_list(request):
    exams = Exam.objects.all()
    context = {
        "exams": exams,
    }
    return render(request, "exams/exam_list.html", context)

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

def delete_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if request.method == "POST":
        exam.delete()
        messages.success(request, "Exam deleted successfully.")
        return redirect("exam_list")
    return render(request, "exams/delete_exam.html", {"exam": exam})

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
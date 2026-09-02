from django.shortcuts import render

from accounts.decorators import staff_required
from .models import Course
from .forms import CourseForm
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

@staff_required
def courses_list(request):
    courses = Course.objects.all()
    context = {'courses': courses}
    return render(request, 'courses/course_list.html', context)

@staff_required
def edit_course(request, id):
    course = get_object_or_404(Course, id=id)

    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)

        if form.is_valid():
            form.save()
            messages.success(request, "Course updated successfully.")
            return redirect("course_list")

    else:
        form = CourseForm(instance=course)

    return render(request, "courses/edit_course.html", {"form": form})

@staff_required
def delete_course(request, id):
    course = get_object_or_404(Course, id=id)

    if request.method == "POST":
        course.delete()
        messages.success(request, "Course deleted successfully.")
        return redirect("course_list")

    return render(request, "courses/delete_course.html", {"course": course})

@staff_required
def add_course(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Course added successfully.")
            return redirect("course_list")
    else:
        form = CourseForm()

    return render(request, "courses/add_course.html", {"form": form})
from django.db.models import Count
from django.shortcuts import render
from students.models import Student
from courses.models import Course
from venues.models import Venue
from exams.models import Exam
from invigilators.models import Invigilator
from allocations.models import Allocation


def dashboard(request):
    total_students = Student.objects.count()
    total_courses = Course.objects.count()
    total_venues = Venue.objects.count()
    total_exams = Exam.objects.count()
    total_invigilators = Invigilator.objects.count()
    total_allocations = Allocation.objects.count()
    department_counts = Student.objects.values('department').annotate(count=Count('id')).order_by('department')
    context = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_venues': total_venues,
        'total_exams': total_exams,
        'total_invigilators': total_invigilators,
        'total_allocations': total_allocations,
        'department_counts': department_counts
    }
    return render(request, 'dashboard/dashboard.html', context)

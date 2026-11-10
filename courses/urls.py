from django.urls import path
from. views import courses_list, edit_course, delete_course, add_course, import_courses, course_students

urlpatterns = [
    path('', courses_list, name='course_list'),
    path('edit/<int:id>/', edit_course, name='edit_course'),
    path('delete/<int:id>/', delete_course, name='delete_course'),
    path('add/', add_course, name='add_course'),
    path('import/', import_courses, name='import_courses'),
    # list of sudents enrolled in a course
    path('<int:id>/students/', course_students, name='course_students'),
]
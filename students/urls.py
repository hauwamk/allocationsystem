from django.urls import path
from .views import delete_student, edit_student, students_list, add_student
from .views import import_students, register_courses
from .bulk_views import bulk_register

urlpatterns = [
    path('', students_list, name='students_list'),
    path('import/', import_students, name='import_students'),
    path('delete/<int:id>/', delete_student, name='delete_student'),
    path('edit/<int:id>/', edit_student, name='edit_student'),
    path('add/', add_student, name='add_student'),
    path('register/<int:id>/', register_courses, name='register_courses'),
    path('bulk-register/', bulk_register, name='bulk_register')
]
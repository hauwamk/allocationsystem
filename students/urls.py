from django.urls import path

from courses import views
from .views import delete_student, edit_student, students_list, add_student, register_courses, student_detail
from .views import import_students
from .bulk_views import bulk_register
from students.views import confirm_registration_replace, import_registrations

urlpatterns = [
    path('', students_list, name='students_list'),
    path('import/', import_students, name='import_students'),
    path('delete/<int:id>/', delete_student, name='delete_student'),
    path('edit/<int:id>/', edit_student, name='edit_student'),
    path('add/', add_student, name='add_student'),
    path('register/<int:id>/', register_courses, name='register_courses'),
    path('bulk-register/', bulk_register, name='bulk_register'),
    path('view/<int:id>/', student_detail, name='student_detail'),
    path("import-registrations/", import_registrations, name="import_registrations"),
    path(
        "import-registrations/confirm/",
        confirm_registration_replace,
        name="confirm_registration_replace",
    ),
]
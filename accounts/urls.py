from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path("login/", views.StudentLoginView.as_view(), name="student_login"),
    path("logout/", LogoutView.as_view(next_page="student_login"), name="student_logout"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path("timetable/print/", views.student_timetable_print, name="student_timetable_print"),

    path("invigilator/login/", views.InvigilatorLoginView.as_view(), name="invigilator_login"),
    path("invigilator/logout/", LogoutView.as_view(next_page="invigilator_login"), name="invigilator_logout"),
    path("invigilator/dashboard/", views.invigilator_dashboard, name="invigilator_dashboard"),

    path("staff/login/", views.ExamOfficerLoginView.as_view(), name="exam_officer_login"),
    path("staff/logout/", LogoutView.as_view(next_page="exam_officer_login"), name="exam_officer_logout"),
    path("import/", views.import_hub, name="import_hub"),

    # Visibly separate Superadmin entry point — its own URL, template and
    # view, distinct from the Exam Officer login above.
    path("superadmin/login/", views.SuperadminLoginView.as_view(), name="superadmin_login"),
    path("superadmin/logout/", LogoutView.as_view(next_page="superadmin_login"), name="superadmin_logout"),

    path("officers/", views.exam_officer_list, name="exam_officer_list"),
    path("officers/create/", views.create_exam_officer, name="create_exam_officer"),
]
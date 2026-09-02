from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path("login/", views.StudentLoginView.as_view(), name="student_login"),
    path("logout/", LogoutView.as_view(next_page="student_login"), name="student_logout"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),

    path("invigilator/login/", views.InvigilatorLoginView.as_view(), name="invigilator_login"),
    path("invigilator/logout/", LogoutView.as_view(next_page="invigilator_login"), name="invigilator_logout"),
    path("invigilator/dashboard/", views.invigilator_dashboard, name="invigilator_dashboard"),

    path("staff/login/", views.ExamOfficerLoginView.as_view(), name="exam_officer_login"),
    path("staff/logout/", LogoutView.as_view(next_page="exam_officer_login"), name="exam_officer_logout"),
    
]
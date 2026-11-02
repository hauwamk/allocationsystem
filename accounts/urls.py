from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy
from . import views

urlpatterns = [
    path("login/", views.StudentLoginView.as_view(), name="student_login"),
    path("logout/", LogoutView.as_view(next_page="student_login"), name="student_logout"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path("timetable/print/", views.student_timetable_print, name="student_timetable_print"),
    path(
        "timetable/download/<str:image_format>/",
        views.student_timetable_image,
        name="student_timetable_image",
    ),
    path(
        "timetable/official/",
        views.student_official_timetables,
        name="student_official_timetables",
    ),
    path(
        "timetable/official/<int:timetable_id>/<str:image_format>/",
        views.student_official_timetable_download,
        name="student_official_timetable_download",
    ),

    path("invigilator/login/", views.InvigilatorLoginView.as_view(), name="invigilator_login"),
    path("invigilator/logout/", LogoutView.as_view(next_page="invigilator_login"), name="invigilator_logout"),
    path("invigilator/dashboard/", views.invigilator_dashboard, name="invigilator_dashboard"),

    path("staff/login/", views.ExamOfficerLoginView.as_view(), name="exam_officer_login"),
    path("staff/logout/", LogoutView.as_view(next_page="exam_officer_login"), name="exam_officer_logout"),
    path("import/", views.import_hub, name="import_hub"),
    path(
        "import/templates/<slug:kind>/",
        views.download_import_template,
        name="download_import_template",
    ),

    # Visibly separate Superadmin entry point — its own URL, template and
    # view, distinct from the Exam Officer login above.
    path("superadmin/login/", views.SuperadminLoginView.as_view(), name="superadmin_login"),
    path("superadmin/logout/", LogoutView.as_view(next_page="superadmin_login"), name="superadmin_logout"),

    path("officers/", views.exam_officer_list, name="exam_officer_list"),
    path("officers/create/", views.create_exam_officer, name="create_exam_officer"),
    path(
        "officers/<int:user_id>/toggle-active/",
        views.toggle_exam_officer_active,
        name="toggle_exam_officer_active",
    ),
    path(
        "officers/<int:user_id>/password/",
        views.reset_exam_officer_password,
        name="reset_exam_officer_password",
    ),

    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url=reverse_lazy("password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
]
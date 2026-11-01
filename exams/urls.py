from django.urls import path
from . import views

urlpatterns = [
    path("", views.exam_list, name="exam_list"),
    path("edit/<int:exam_id>/", views.edit_exam, name="edit_exam"),
    path("delete/<int:exam_id>/", views.delete_exam, name="delete_exam"),
    path("add/", views.add_exam, name="add_exam"),
    path("allocate/<int:exam_id>/", views.allocate_exam_view, name="allocate_exam"),
    path("allocate/<int:exam_id>/clear/", views.clear_exam_allocation_view, name="clear_exam_allocation"),
    path("allocate-all/", views.allocate_all_exams_view, name="allocate_all_exams"),

    path("timetables/", views.timetable_list, name="timetable_list"),
    path("timetables/create/", views.timetable_create, name="timetable_create"),
    path("timetables/<int:timetable_id>/", views.timetable_detail, name="timetable_detail"),
    path("timetables/<int:timetable_id>/upload/", views.timetable_upload_csv, name="timetable_upload_csv"),
    path("timetables/<int:timetable_id>/replace/confirm/", views.confirm_timetable_replace, name="confirm_timetable_replace"),
    path("timetables/<int:timetable_id>/file/", views.timetable_upload_file, name="timetable_upload_file"),
    path("timetables/<int:timetable_id>/publish/", views.publish_timetable, name="publish_timetable"),
    path("timetables/<int:timetable_id>/unpublish/", views.unpublish_timetable, name="unpublish_timetable"),
    path("timetables/<int:timetable_id>/archive/", views.archive_timetable, name="archive_timetable"),
    path("timetables/<int:timetable_id>/restore/", views.restore_timetable, name="restore_timetable"),
    path("timetables/<int:timetable_id>/delete/", views.delete_timetable, name="delete_timetable"),
]
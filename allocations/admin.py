from django.contrib import admin
from .models import ExamSession, Allocation


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ("exam", "venue", "invigilator")
    list_filter = ("venue", "invigilator")


@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ("student", "exam_session", "seating_number")
    list_filter = ("exam_session__venue",)
    search_fields = ("student__registration_number",)
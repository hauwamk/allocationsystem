from django.urls import path

from .views import delete_invigilator, edit_invigilator, invigilators_list, add_invigilator, import_invigilators

urlpatterns = [
    path('', invigilators_list, name='invigilators_list'),
    path('edit/<int:id>/', edit_invigilator, name='edit_invigilator'),
    path('delete/<int:id>/', delete_invigilator, name='delete_invigilator'),
    path('import/', import_invigilators, name='import_invigilators'),
    path('add/', add_invigilator, name='add_invigilator'),

]

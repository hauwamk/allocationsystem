from django.urls import path
from .views import dashboard, department_list, department_detail

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('departments/', department_list, name='department_list'),
    path('departments/<str:code>/', department_detail, name='department_detail'),
]
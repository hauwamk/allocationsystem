from django.urls import path
from . import views

urlpatterns = [
    path('', views.session_list, name='session_list'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
]
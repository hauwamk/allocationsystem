from django.urls import path
from .views import delete_venue, edit_venue, venue_list, add_venue

urlpatterns = [
    path('', venue_list, name='venue_list'),
    path('edit/<int:id>/', edit_venue, name='edit_venue'),
    path('delete/<int:id>/', delete_venue, name='delete_venue'),
    path('add/', add_venue, name='add_venue')
]
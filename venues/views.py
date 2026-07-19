
from django.shortcuts import render, redirect, get_object_or_404

from django.contrib import messages

from venues.forms import VenueForm
from .models import Venue

#returns a list of all venues
def venue_list(request):
    venues = Venue.objects.all()

    context = {
        "venues": venues
    }

    return render(request, "venues/venue_list.html", context)

def edit_venue(request, id):
    venue = get_object_or_404(Venue, id=id)

    if request.method == "POST":
        form = VenueForm(request.POST, instance=venue)

        if form.is_valid():
            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect("venue_list")

    else:
        form = VenueForm(instance=venue)

    return render(request, "venues/edit_venue.html", {"form": form})

def delete_venue(request, id):
    venue = get_object_or_404(Venue, id=id)

    if request.method == "POST":
        venue.delete()
        messages.success(request, "Venue deleted successfully.")
        return redirect("venue_list")

    return render(request, "venues/delete_venue.html", {"venue": venue})

def add_venue(request):
    if request.method == "POST":
        form = VenueForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Venue added successfully.")
            return redirect("venue_list")
    else:
        form = VenueForm()

    return render(request, "venues/add_venue.html", {"form": form})
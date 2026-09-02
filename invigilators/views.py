from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import staff_required
from .forms import InvigilatorForm
from .models import Invigilator


@staff_required
def invigilators_list(request):
    invigilators = Invigilator.objects.all()
    context = {"invigilators": invigilators}
    return render(request, "invigilator/invigilator_list.html", context)


@staff_required
def edit_invigilator(request, id):
    invigilator_instance = get_object_or_404(Invigilator, id=id)

    if request.method == "POST":
        form = InvigilatorForm(request.POST, instance=invigilator_instance)

        if form.is_valid():
            form.save()
            messages.success(request, "Invigilator updated successfully.")
            return redirect("invigilators_list")

    else:
        form = InvigilatorForm(instance=invigilator_instance)

    return render(request, "invigilator/edit_invigilator.html", {"form": form})


@staff_required
def delete_invigilator(request, id):
    invigilator_instance = get_object_or_404(Invigilator, id=id)

    if request.method == "POST":
        invigilator_instance.delete()
        messages.success(request, "Invigilator deleted successfully.")
        return redirect("invigilators_list")

    return render(request, "invigilator/delete_invigilator.html", {"invigilator": invigilator_instance})

@staff_required
def add_invigilator(request):
    if request.method == "POST":
        form = InvigilatorForm(request.POST)
        if form.is_valid():
            invigilator = form.save(commit=False)
            user, _ = User.objects.get_or_create(username=invigilator.staff_id)
            user.set_password(invigilator.staff_id)
            user.save()
            invigilator.user = user
            invigilator.save()
            messages.success(request, "Invigilator added successfully.")
            return redirect("invigilators_list")
    else:
        form = InvigilatorForm()

    return render(request, "invigilator/add_invigilator.html", {"form": form})
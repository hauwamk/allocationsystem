import csv
import re
from io import TextIOWrapper

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import staff_required
from .forms import InvigilatorForm, InvigilatorImportForm
from .models import Invigilator


def _normalize_header(header):
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _normalize_row(row):
    normalized = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[_normalize_header(key)] = value or ""
    return normalized


def _get_field(row, *possible_names):
    normalized_row = _normalize_row(row)
    for name in possible_names:
        value = normalized_row.get(_normalize_header(name), "")
        if value:
            return value.strip()
    return ""


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


@staff_required
def import_invigilators(request):
    """
    CSV columns expected: Staff ID, Full Name, Phone Number.
    Each newly-created invigilator gets a login automatically (username
    and starting password = staff ID), same as add_invigilator.
    """
    if request.method == "POST":
        form = InvigilatorImportForm(request.POST, request.FILES)

        if form.is_valid():
            csv_file = request.FILES["csv_file"]
            file = TextIOWrapper(csv_file.file, encoding="utf-8")
            reader = csv.DictReader(file)

            imported = 0
            skipped = 0

            if not reader.fieldnames:
                messages.error(request, "The uploaded file does not contain any headers.")
            else:
                for row in reader:
                    staff_id = _get_field(row, "staff_id", "staff id")
                    if not staff_id:
                        continue

                    full_name = _get_field(row, "full_name", "full name")
                    phone_number = _get_field(row, "phone_number", "phone number", "phone")

                    invigilator, created = Invigilator.objects.get_or_create(
                        staff_id=staff_id,
                        defaults={
                            "full_name": full_name,
                            "phone_number": phone_number,
                        },
                    )

                    if created:
                        user, _ = User.objects.get_or_create(username=staff_id)
                        user.set_password(staff_id)
                        user.save()
                        invigilator.user = user
                        invigilator.save()
                        imported += 1
                    else:
                        skipped += 1

                messages.success(
                    request,
                    f"Import completed! Imported: {imported}, Skipped: {skipped}",
                )
                return redirect("invigilators_list")

    else:
        form = InvigilatorImportForm()

    return render(request, "invigilator/import_invigilators.html", {"form": form})
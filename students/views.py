import datetime

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction  # NEW: lets us save many rows all-or-nothing
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import staff_required
from courses.models import Course
from exam.departments import department_codes
from exam.imports import (
    ImportFileError,
    get_field as _get_field,
    read_tabular_upload,
)
from exam.pagination import paginate
# NEW: CourseListImportForm is the form for "pick a course + upload a file"
from .forms import StudentEditForm, StudentImportForm, RegisterCourseForm, CourseListImportForm
from .models import Student, Registration
from allocations.models import Allocation

from django.shortcuts import get_object_or_404, redirect

@staff_required
def students_list(request):
    students = Student.objects.all().order_by("registration_number")
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    gender = request.GET.get("gender", "").strip()

    if query:
        students = students.filter(
            Q(registration_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if department:
        students = students.filter(department__in=department_codes(department))
    if level:
        students = students.filter(level=level)
    if gender:
        students = students.filter(gender=gender)

    page_obj = paginate(request, students)
    context = {
        "students": page_obj,
        "page_obj": page_obj,
        "departments": Student.DEPARTMENT_CHOICES,
        "levels": Student.LEVEL_CHOICES,
        "genders": Student.GENDER_CHOICES,
    }
    return render(request, "students/student_list.html", context)

@staff_required
def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                data = read_tabular_upload(request.FILES["csv_file"])
            except ImportFileError as exc:
                messages.error(request, str(exc))
                data = None

            imported = 0
            skipped = 0
            linked = 0

            if data is not None and not data.headers:
                messages.error(request, "The uploaded file does not contain any headers.")
            elif data is not None:
                for row in data.rows:
                    registration_number = _get_field(row, "registration_number", "registration number")
                    if not registration_number:
                        continue

                    first_name = _get_field(row, "first_name", "first name")
                    last_name = _get_field(row, "last_name", "last name")
                    level = _get_field(row, "level")
                    department = _get_field(row, "department")
                    gender = _get_field(row, "gender")
                    email = _get_field(row, "email")

                    student, created = Student.objects.get_or_create(
                        registration_number=registration_number,
                        defaults={
                            "first_name": first_name,
                            "last_name": last_name,
                            "level": level,
                            "department": department,
                            "gender": gender,
                            "email": email,
                        },
                    )

                    # Existing rows may predate login creation, so fix both new and old records.
                    if student.user_id is None:
                        user, _ = User.objects.get_or_create(username=registration_number)
                        user.set_password(registration_number)
                        user.save()
                        student.user = user
                        student.save(update_fields=["user"])
                        linked += 1

                    if created:
                        imported += 1
                    else:
                        skipped += 1

                messages.success(
                    request,
                    f"Import completed! Imported: {imported}, Skipped: {skipped}, "
                    f"Logins created/linked: {linked}",
                )

    else:
        form = StudentImportForm()

    return render(
        request,
        "students/importstudentslist.html",
        {"form": form},
    )
@staff_required
def delete_student(request, id):
    student = get_object_or_404(Student, id=id)

    if request.method == "POST":
        student.delete()
        messages.success(request, "Student deleted successfully.")
        return redirect("students_list")

    return render(request, "students/delete_student.html", {"student": student})

@staff_required
def edit_student(request, id):
    student = get_object_or_404(Student, id=id)

    if request.method == "POST":
        form = StudentEditForm(request.POST, instance=student)

        if form.is_valid():
            form.save()

            # Keep the student's login in sync with their registration
            # number. Username/password were only ever set ONCE, at
            # creation — so if an officer corrects a student's reg
            # number here (e.g. fixing it to the new official format),
            # the login must be updated to match, or the student gets
            # locked out under their old (now-wrong) credentials.
            from django.contrib.auth.models import User
            if student.user:
                student.user.username = student.registration_number
                student.user.set_password(student.registration_number)
                student.user.save()
            else:
                # Safety net: an older student record with no linked
                # login yet — create one now, same as add_student does.
                user, _ = User.objects.get_or_create(username=student.registration_number)
                user.set_password(student.registration_number)
                user.save()
                student.user = user
                student.save()

            messages.success(request, "Student updated successfully.")
            return redirect("students_list")

    else:
        form = StudentEditForm(instance=student)

    return render(request, "students/edit_student.html", {"form": form})

@staff_required
def add_student(request):
    if request.method == "POST":
        form = StudentEditForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            from django.contrib.auth.models import User
            user, _ = User.objects.get_or_create(username=student.registration_number)
            user.set_password(student.registration_number)
            user.save()
            student.user = user
            student.save()
            messages.success(request, "Student added successfully.")
            return redirect("students_list")
    else:
        form = StudentEditForm()

    return render(request, "students/add_student.html", {"form": form})

@staff_required
def register_courses(request, id):
    student = get_object_or_404(Student, id=id)
    current_course_ids = Registration.objects.filter(student=student).values_list("course_id", flat=True)

    if request.method == "POST":
        form = RegisterCourseForm(request.POST)
        if form.is_valid():
            selected_courses = form.cleaned_data["courses"]
            Registration.objects.filter(student=student).exclude(course__in=selected_courses).delete()
            for course in selected_courses:
                Registration.objects.get_or_create(student=student, course=course)
            messages.success(request, f"Updated course registrations for {student.registration_number}.")
            return redirect("students_list")
    else:
        form = RegisterCourseForm(initial={"courses": current_course_ids})

    return render(request, "students/register_courses.html", {"form": form, "student": student})

@staff_required
def student_detail(request, id):
    """
    View page: a single student's full profile in one place — their
    basic info, every course they're registered for, and every exam
    seat they've actually been allocated.
    """
    student = get_object_or_404(Student, id=id)
    registrations = Registration.objects.filter(student=student).select_related("course")
    allocations = Allocation.objects.filter(student=student).select_related(
        "exam_session__exam__course", "exam_session__venue"
    )
    return render(request, "students/student_detail.html", {
        "student": student,
        "registrations": registrations,
        "allocations": allocations,
    })

def _names_match(file_name, student):
    """
    Loose name check: True if every word in the name from the uploaded file
    appears somewhere in the student's name in the system. Order and
    upper/lower case don't matter, so "KULIYA hauwa" matches "Hauwa Kuliya".
    """
    system_words = f"{student.first_name} {student.last_name}".lower().split()
    # Every word from the file must be found among the system's words
    return all(word in system_words for word in file_name.lower().split())


PENDING_REPLACE_SESSION_KEY = "pending_registration_replace"
PENDING_REPLACE_MAX_AGE = datetime.timedelta(hours=1)


@staff_required
def import_registrations(request):
    """
    Upload the list of students registered for ONE course.

    The officer picks a course from a dropdown and uploads a CSV or Excel
    file with the columns reg_no and full_name (one student per row). Every
    student found in the system is registered for that course.

    Replace mode never deletes straight from the upload. It first shows a
    preview of exactly who will be added and removed; the change is only
    applied after the officer confirms. A file that matches nobody is
    rejected outright, so a wrong reg format can't empty a course.
    """
    summary = None
    preview = None

    if request.method == "POST":
        form = CourseListImportForm(request.POST, request.FILES)

        # A fresh upload always replaces any older preview waiting in this session.
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)

        if form.is_valid():
            course = form.cleaned_data["course"]
            replace = form.cleaned_data["replace_existing"]

            try:
                data = read_tabular_upload(request.FILES["csv_file"])
            except ImportFileError as exc:
                messages.error(request, str(exc))
                data = None

            if data is not None and not data.headers:
                messages.error(request, "The uploaded file does not contain any headers.")

            elif data is not None and replace and Allocation.objects.filter(
                exam_session__exam__course=course
            ).exists():
                # Safety rule: if seats were already given out for this course,
                # removing students from its list would leave seats belonging
                # to students who are no longer registered. So we refuse.
                messages.error(
                    request,
                    "Seats have already been allocated for this course, so its list can't be "
                    "replaced. Upload without 'Replace' to add students instead.",
                )

            elif data is not None:
                # Build a lookup of every student by registration number,
                # in lowercase, so CST/22/SWE/00858 matches cst/22/swe/00858.
                # One database query here is much faster than one per row.
                students_by_reg = {
                    s.registration_number.strip().lower(): s for s in Student.objects.all()
                }

                # The students already registered for THIS course
                existing_ids = set(
                    Registration.objects.filter(course=course).values_list("student_id", flat=True)
                )

                to_add = []          # Student objects to register
                listed_ids = set()   # students seen in the file (to catch repeats)
                already = bad_rows = 0
                unknown = []         # (reg_no, name) pairs not found in the system
                name_mismatch = []   # students found, but the name in the file looks different

                for row in data.rows:
                    # Read the reg number from the row. The extra names let the
                    # file use other common column headings too.
                    reg_no = _get_field(
                        row, "reg_no", "registration_number", "registration number",
                        "matric_number", "matric number",
                    )
                    # Read the student's full name (may be empty if the column is missing)
                    full_name = _get_field(
                        row, "full_name", "full name", "name", "student_name", "student name",
                    )

                    # Blank row: nothing to read, count it and move on
                    if not reg_no:
                        bad_rows += 1
                        continue

                    # Find the student. None means no such student exists yet.
                    student = students_by_reg.get(reg_no.lower())
                    if student is None:
                        unknown.append((reg_no, full_name))
                        continue

                    # The same student listed twice in one file: ignore the repeat
                    if student.id in listed_ids:
                        continue
                    listed_ids.add(student.id)

                    # If the file gave a name, check it against the system's name.
                    # A mismatch usually means a typo in the reg number.
                    if full_name and not _names_match(full_name, student):
                        name_mismatch.append((reg_no, full_name, f"{student.first_name} {student.last_name}"))

                    if student.id in existing_ids:
                        # Already registered for this course: nothing to do
                        already += 1
                    else:
                        # New: keep it for the preview or the append below
                        to_add.append(student)

                added = len(to_add)
                remove_ids = sorted(existing_ids - listed_ids)

                if replace and not listed_ids:
                    # A wrong column or reg format must never wipe the existing list.
                    messages.error(
                        request,
                        f"No student in that file matched a registration number in the system, "
                        f"so the existing list for {course.course_code} was left unchanged. "
                        "Check the reg numbers and upload again.",
                    )
                    summary = {
                        "course": course,
                        "added": 0,
                        "already": 0,
                        "removed": 0,
                        "bad_rows": bad_rows,
                        "unknown": unknown,
                        "name_mismatch": name_mismatch,
                        "no_match": True,
                    }

                elif replace:
                    # Hold the exact add/remove sets until the officer confirms.
                    request.session[PENDING_REPLACE_SESSION_KEY] = {
                        "course_id": course.id,
                        "add_ids": [student.id for student in to_add],
                        "remove_ids": remove_ids,
                        "filename": request.FILES["csv_file"].name,
                        "created_at": timezone.now().isoformat(),
                    }
                    preview = {
                        "course": course,
                        "filename": request.FILES["csv_file"].name,
                        "added": added,
                        "already": already,
                        "removed": len(remove_ids),
                        "bad_rows": bad_rows,
                        "unknown": unknown,
                        "name_mismatch": name_mismatch,
                        "to_add": sorted(to_add, key=lambda s: s.registration_number),
                        "to_remove": list(
                            Student.objects.filter(id__in=remove_ids)
                            .order_by("registration_number")
                        ),
                    }

                else:
                    # Append mode only ever adds rows, so it is safe to save now.
                    with transaction.atomic():
                        Registration.objects.bulk_create(
                            [Registration(student=student, course=course) for student in to_add],
                            ignore_conflicts=True,
                        )
                    summary = {
                        "course": course,
                        "added": added,
                        "already": already,
                        "removed": 0,
                        "bad_rows": bad_rows,
                        "unknown": unknown,
                        "name_mismatch": name_mismatch,
                    }
                    messages.success(
                        request,
                        f"{course.course_code}: added {added}, already registered {already}.",
                    )
    else:
        # First visit to the page: show an empty form
        form = CourseListImportForm()

    return render(
        request,
        "students/import_registrations.html",
        {"form": form, "summary": summary, "preview": preview},
    )


@staff_required
def confirm_registration_replace(request):
    """Applies the replacement shown on the preview page, after re-checking safety."""
    pending = request.session.get(PENDING_REPLACE_SESSION_KEY)

    if request.method != "POST":
        return redirect("import_registrations")

    if request.POST.get("action") == "cancel":
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
        messages.info(request, "Replacement cancelled. The existing list was left unchanged.")
        return redirect("import_registrations")

    if request.POST.get("action") != "confirm":
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
        messages.error(request, "Nothing was changed: the replacement was not confirmed.")
        return redirect("import_registrations")

    if not pending:
        messages.error(
            request,
            "There is no replacement waiting for confirmation. Upload the file again.",
        )
        return redirect("import_registrations")

    try:
        created_at = datetime.datetime.fromisoformat(pending["created_at"])
    except (KeyError, TypeError, ValueError):
        created_at = None

    if created_at is None or timezone.now() - created_at > PENDING_REPLACE_MAX_AGE:
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
        messages.error(request, "That replacement review has expired. Upload the file again.")
        return redirect("import_registrations")

    course = Course.objects.filter(id=pending.get("course_id")).first()
    if course is None:
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
        messages.error(request, "That course no longer exists. Nothing was changed.")
        return redirect("import_registrations")

    if Allocation.objects.filter(exam_session__exam__course=course).exists():
        request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
        messages.error(
            request,
            "Seats have already been allocated for this course, so its list can't be replaced. "
            "Upload without 'Replace' to add students instead.",
        )
        return redirect("import_registrations")

    add_ids = [int(student_id) for student_id in pending.get("add_ids", [])]
    remove_ids = [int(student_id) for student_id in pending.get("remove_ids", [])]

    with transaction.atomic():
        students = list(Student.objects.filter(id__in=add_ids))
        Registration.objects.bulk_create(
            [Registration(student=student, course=course) for student in students],
            ignore_conflicts=True,
        )
        to_remove = Registration.objects.filter(course=course, student_id__in=remove_ids)
        removed = to_remove.count()
        to_remove.delete()

    request.session.pop(PENDING_REPLACE_SESSION_KEY, None)
    messages.success(
        request,
        f"{course.course_code}: added {len(students)}, removed {removed}.",
    )
    return redirect("import_registrations")
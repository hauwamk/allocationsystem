from functools import wraps
from django.contrib.auth.views import redirect_to_login


def staff_required(view_func):
    """
    Protects an admin/exam-officer view. Redirects to the exam officer
    login page if the user isn't logged in, or isn't marked as staff.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect_to_login(request.get_full_path(), login_url="exam_officer_login")
        return view_func(request, *args, **kwargs)
    return wrapper


def superadmin_required(view_func):
    """
    Protects a Superadmin-only view (currently: creating and managing
    Exam Officer accounts). Superadmin = Django's is_superuser flag —
    the account created via 'python manage.py createsuperuser', or any
    account a Superadmin later promotes.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect_to_login(request.get_full_path(), login_url="exam_officer_login")
        return view_func(request, *args, **kwargs)
    return wrapper
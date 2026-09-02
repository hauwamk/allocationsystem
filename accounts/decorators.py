from functools import wraps
from django.contrib.auth.views import redirect_to_login


def staff_required(view_func):
    """
    Protects an admin/exam-officer view. Redirects to the exam officer
    login page if the user isn't logged in, or isn't marked as staff
    (is_staff=True — the same flag set on accounts made with
    'python manage.py createsuperuser').
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect_to_login(request.get_full_path(), login_url="exam_officer_login")
        return view_func(request, *args, **kwargs)
    return wrapper
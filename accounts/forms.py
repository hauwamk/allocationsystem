from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class ExamOfficerCreationForm(UserCreationForm):
    """
    Same username/password/confirm-password form Django uses for its own
    admin, reused here so a Superadmin can create a new Exam Officer
    account without touching the command line. is_staff gets set to True
    (and is_superuser stays False) in the view after this form saves.
    """
    class Meta:
        model = User
        fields = ["username"]
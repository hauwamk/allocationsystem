from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from students.models import Student


class Command(BaseCommand):
    help = (
        "Creates a login (User) for every existing Student that doesn't have "
        "one yet. Username = registration number, starting password = "
        "registration number too."
    )

    def handle(self, *args, **options):
        created = 0
        for student in Student.objects.filter(user__isnull=True):
            user, made = User.objects.get_or_create(username=student.registration_number)
            user.set_password(student.registration_number)
            user.save()
            student.user = user
            student.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Created/linked {created} student login(s)."))
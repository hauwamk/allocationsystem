from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from invigilators.models import Invigilator


class Command(BaseCommand):
    help = (
        "Creates a login (User) for every existing Invigilator that doesn't "
        "have one yet. Username = staff ID, starting password = staff ID too."
    )

    def handle(self, *args, **options):
        created = 0
        for invigilator in Invigilator.objects.filter(user__isnull=True):
            user, _ = User.objects.get_or_create(username=invigilator.staff_id)
            user.set_password(invigilator.staff_id)
            user.save()
            invigilator.user = user
            invigilator.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Created/linked {created} invigilator login(s)."))
"""
Allocation logic for the allocations app.

Flow for one exam:

1. Find registered students (via students.models.Registration).

2. Pick venues that aren't already booked for another exam at the same
date/time, preferring the smallest hall that seats the whole group and
using the least-used one to break ties (see
_order_venues_for_allocation below).

3. For each venue, pair it with an invigilator who isn't already busy
at that date/time (and isn't already used in this same run), also
ordered LEAST-USED FIRST, for the same reason.

4. Shuffle the registered students, then seat them into that venue,
seating_number 1..capacity, until everyone registered has a seat.

Re-running allocate_exam() for the same exam is safe — it clears any
previous ExamSession/Allocation rows for that exam first.

Busy checks treat an exam as occupying its start time plus its duration, so
back-to-back exams can share a venue or invigilator but overlapping ones
cannot.
"""
import random

from django.db import transaction

from exam.scheduling import exams_overlap
from students.models import Registration
from venues.models import Venue
from invigilators.models import Invigilator
from .models import ExamSession, Allocation


def get_registered_students(exam):
    """All students registered for the course this exam covers."""
    return [
        reg.student
        for reg in Registration.objects.filter(course=exam.course).select_related("student")
    ]


def invigilator_is_busy(invigilator, exam):
    """True if the invigilator is already staffing an exam that overlaps this one."""
    sessions = (
        ExamSession.objects.filter(
            invigilator=invigilator, exam__exam_date=exam.exam_date,
        )
        .exclude(exam=exam)
        .select_related("exam")
    )
    return any(exams_overlap(session.exam, exam) for session in sessions)


def venue_is_busy(venue, exam):
    """True if the venue is already booked for an exam that overlaps this one."""
    sessions = (
        ExamSession.objects.filter(
            venue=venue, exam__exam_date=exam.exam_date,
        )
        .exclude(exam=exam)
        .select_related("exam")
    )
    return any(exams_overlap(session.exam, exam) for session in sessions)


def _order_venues_for_allocation(venues, needed):
    """
    Venues that can seat the whole group come first: the smallest hall that
    still fits, so a five-student exam doesn't take a 120-seat theatre while
    small rooms sit empty. Least-used breaks ties between halls of the same
    size. Venues too small for the group follow, largest first, so the
    overflow needs as few extra rooms as possible.
    """
    usage_counts = {v.id: ExamSession.objects.filter(venue=v).count() for v in venues}
    fitting = sorted(
        (v for v in venues if v.capacity >= needed),
        key=lambda v: (v.capacity, usage_counts[v.id]),
    )
    overflowing = sorted(
        (v for v in venues if v.capacity < needed),
        key=lambda v: (-v.capacity, usage_counts[v.id]),
    )
    return fitting + overflowing


def _order_invigilators_by_load(invigilators):
    """
    Same idea as _order_venues_by_load, but for invigilators: whoever
    has done the fewest duties so far gets offered the next one first.
    """
    usage_counts = {inv.id: ExamSession.objects.filter(invigilator=inv).count() for inv in invigilators}
    return sorted(invigilators, key=lambda inv: usage_counts[inv.id])


@transaction.atomic
def allocate_exam(exam, venues=None, invigilators=None):
    """
    Full allocation for a single exam. Raises ValueError if there isn't
    enough free venue capacity, or not enough free invigilators to staff
    the venues that get used.
    """
    students = get_registered_students(exam)
    if not students:
        raise ValueError(f"No students are registered for {exam.course.course_code}.")

    random.shuffle(students)

    # Idempotent: wipe this exam's previous sessions (Allocation rows cascade).
    ExamSession.objects.filter(exam=exam).delete()

    candidate_venues = _order_venues_for_allocation(
        list(venues or Venue.objects.all()), len(students)
    )
    free_venues = [v for v in candidate_venues if not venue_is_busy(v, exam)]

    candidate_invigilators = _order_invigilators_by_load(list(invigilators or Invigilator.objects.all()))

    remaining = students[:]
    sessions_created = []
    used_invigilator_ids = set()

    for venue in free_venues:
        if not remaining:
            break

        free_invigilator = next(
            (inv for inv in candidate_invigilators
             if inv.id not in used_invigilator_ids and not invigilator_is_busy(inv, exam)),
            None,
        )
        if free_invigilator is None:
            continue  # no one free for this venue right now — try the next venue

        session = ExamSession.objects.create(exam=exam, venue=venue, invigilator=free_invigilator)
        sessions_created.append(session)
        used_invigilator_ids.add(free_invigilator.id)

        batch, remaining = remaining[:venue.capacity], remaining[venue.capacity:]
        Allocation.objects.bulk_create([
            Allocation(student=student, exam_session=session, seating_number=i + 1)
            for i, student in enumerate(batch)
        ])

    if remaining:
        raise ValueError(
            f"Not enough free venue capacity/invigilators for "
            f"{exam.course.course_code}: {len(remaining)} student(s) "
            f"could not be seated. Add more venues or free up invigilators."
        )

    return sessions_created


def allocate_semester(exams):
    """
    Bulk allocation across several exams (your "planned: bulk allocation
    for all examinations in a semester" feature). Runs allocate_exam() for
    each and collects failures instead of stopping at the first one, so
    one exam without enough capacity doesn't block the rest.
    """
    results = {"succeeded": [], "failed": []}
    for exam in exams:
        try:
            sessions = allocate_exam(exam)
            results["succeeded"].append((exam, sessions))
        except ValueError as e:
            results["failed"].append((exam, str(e)))
    return results
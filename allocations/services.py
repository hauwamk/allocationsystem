"""
Allocation logic for the allocations app.

Flow for one exam:

1. Find registered students (via students.models.Registration).


2. Pick venues that aren't already booked for another exam at the same
date/time, in order of largest capacity first.


3. For each venue, pair it with an invigilator who isn't already busy
at that date/time (and isn't already used in this same run).


4. Seat students into that venue, seating_number 1..capacity, until
everyone registered has a seat.



Re-running allocate_exam() for the same exam is safe — it clears any
previous ExamSession/Allocation rows for that exam first.

Clash detection uses Exam.exam_date and Exam.exam_time.
"""
from django.db import transaction

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
    """True if already assigned to a session for a different exam at the same date/time."""
    return ExamSession.objects.filter(
        invigilator=invigilator,
        exam__exam_date=exam.exam_date,
        exam__exam_time=exam.exam_time,
    ).exclude(exam=exam).exists()

def venue_is_busy(venue, exam):
    """True if already booked for a different exam at the same date/time."""
    return ExamSession.objects.filter(
        venue=venue,
        exam__exam_date=exam.exam_date,
        exam__exam_time=exam.exam_time,
    ).exclude(exam=exam).exists()

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

    # Idempotent: wipe this exam's previous sessions (Allocation rows cascade).  
    ExamSession.objects.filter(exam=exam).delete()  

    candidate_venues = list(venues or Venue.objects.order_by("-capacity"))  
    free_venues = [v for v in candidate_venues if not venue_is_busy(v, exam)]  

    candidate_invigilators = list(invigilators or Invigilator.objects.all())  

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
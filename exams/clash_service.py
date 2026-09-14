"""
Clash detection: finds students who would end up with two exams at the
same date and time.

This matters because a student can be registered for several courses,
and nothing stops two of those courses from being scheduled into the
same exam slot by accident. This function catches that before it
becomes a real problem on exam day.
"""
from students.models import Registration
from .models import Exam


def find_clashes(exam):
    """
    Checks one exam against every other exam in the system and returns
    a list of clashes: cases where a student registered for THIS exam's
    course is also registered for a DIFFERENT course whose exam falls on
    the exact same date and time.

    Returns a list of dicts, one per clash found:
        {"student": <Student>, "exam_a": <Exam>, "exam_b": <Exam>}
    An empty list means no clashes were found.
    """
    # Step 1: find every student sitting THIS exam (i.e. registered for
    # its course). select_related pulls the Student row in the same
    # query instead of a separate query per row, so this stays fast even
    # with many registrations.
    students_in_this_exam = Registration.objects.filter(
        course=exam.course
    ).select_related("student")

    clashes = []

    for registration in students_in_this_exam:
        student = registration.student

        # Step 2: for this student, look at every OTHER course they're
        # registered for (excluding the one we're already checking).
        other_registrations = Registration.objects.filter(
            student=student
        ).exclude(course=exam.course)

        for other_registration in other_registrations:
            # Step 3: does that other course have its OWN exam scheduled
            # at the exact same date and time as the exam we're
            # checking? If so, this student physically cannot sit both —
            # that's the clash.
            conflicting_exam = Exam.objects.filter(
                course=other_registration.course,
                exam_date=exam.exam_date,
                exam_time=exam.exam_time,
            ).exclude(id=exam.id).first()

            if conflicting_exam:
                clashes.append({
                    "student": student,
                    "exam_a": exam,
                    "exam_b": conflicting_exam,
                })

    return clashes
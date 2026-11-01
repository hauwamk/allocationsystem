"""Shared exam-time arithmetic for clash and venue/invigilator checks."""
from datetime import datetime, timedelta

# An exam entered without a usable duration still occupies its start minute,
# so it is not silently exempt from overlap checks.
MINIMUM_DURATION_MINUTES = 1


def exam_interval(exam):
    """The exam's start and end as datetimes, allowing for its duration."""
    start = datetime.combine(exam.exam_date, exam.exam_time)
    if exam.duration and exam.duration > 0:
        minutes = exam.duration
    else:
        minutes = MINIMUM_DURATION_MINUTES
    return start, start + timedelta(minutes=minutes)


def exams_overlap(exam_a, exam_b):
    """
    True when the two exams fall on the same date and their times overlap.

    Touching slots (one ends exactly when the next starts) do not overlap.
    """
    if exam_a.exam_date != exam_b.exam_date:
        return False
    start_a, end_a = exam_interval(exam_a)
    start_b, end_b = exam_interval(exam_b)
    return start_a < end_b and start_b < end_a

"""
Clash detection: students who would be entered for two exams whose times
overlap on the same day.

A student can be registered for several courses, and nothing stops two of
those courses from being scheduled into overlapping time by accident. This
module is the only clash implementation: the views call it before warning
about a saved exam and before publishing a batch.

Only exams students can actually see are compared — the batch being built
and batches that are already published. A draft in another batch cannot
clash with anything yet, and an archived batch is retired.
"""
from collections import defaultdict
from itertools import combinations

from django.db.models import Q

from exam.scheduling import exams_overlap
from students.models import Registration

from .models import Exam


def _clashes_among(exams):
    """
    Every (student, overlapping exam pair) clash among `exams`.

    Two queries — the exam list and one registration query — then all
    comparisons happen in memory, so the cost does not grow with
    exams x registrations x courses.
    """
    exams = list(exams)
    if len(exams) < 2:
        return []

    exams_by_course = defaultdict(list)
    for exam in exams:
        exams_by_course[exam.course_id].append(exam)

    student_courses = defaultdict(set)
    students = {}
    for registration in Registration.objects.filter(
        course_id__in=exams_by_course
    ).select_related("student"):
        student_courses[registration.student_id].add(registration.course_id)
        students[registration.student_id] = registration.student

    # Students who take the same courses share the same exam pairs, so each
    # pair of courses is compared once for the whole group.
    students_by_courses = defaultdict(list)
    for student_id, course_ids in student_courses.items():
        if len(course_ids) > 1:
            students_by_courses[tuple(sorted(course_ids))].append(student_id)

    clashes = []
    for course_ids, student_ids in students_by_courses.items():
        for course_a, course_b in combinations(course_ids, 2):
            for exam_a in exams_by_course[course_a]:
                for exam_b in exams_by_course[course_b]:
                    if not exams_overlap(exam_a, exam_b):
                        continue
                    if exam_a.exam_time <= exam_b.exam_time:
                        first, second = exam_a, exam_b
                    else:
                        first, second = exam_b, exam_a
                    for student_id in student_ids:
                        clashes.append({
                            "student": students[student_id],
                            "exam_a": first,
                            "exam_b": second,
                        })
    return clashes


def find_clashes(exam):
    """
    Clashes involving one exam.

    A batch exam is compared with the rest of its batch and with every
    published batch. A standalone exam is compared with the published
    batches only, because students cannot see standalone exams.
    """
    published = Q(timetable__status="PUBLISHED")
    if exam.timetable_id is not None:
        scope = Exam.objects.filter(Q(timetable_id=exam.timetable_id) | published)
    else:
        scope = Exam.objects.filter(Q(id=exam.id) | published)

    clashes = []
    for clash in _clashes_among(scope.select_related("course")):
        if clash["exam_a"].id == exam.id:
            clashes.append(clash)
        elif clash["exam_b"].id == exam.id:
            clashes.append({
                "student": clash["student"],
                "exam_a": exam,
                "exam_b": clash["exam_a"],
            })
    return clashes


def find_timetable_clashes(timetable):
    """
    Clashes that publishing this batch would expose to students: pairs where
    at least one exam belongs to the batch. Clashes between two published
    batches elsewhere are not this batch's problem.
    """
    batch_exam_ids = set(timetable.exams.values_list("id", flat=True))
    if not batch_exam_ids:
        return []

    scope = Exam.objects.filter(
        Q(timetable=timetable) | Q(timetable__status="PUBLISHED")
    ).select_related("course")

    return [
        clash
        for clash in _clashes_among(scope)
        if clash["exam_a"].id in batch_exam_ids
        or clash["exam_b"].id in batch_exam_ids
    ]

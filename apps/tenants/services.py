"""Kindergarten, school year, group and staffing rules — RFP §2.1, §3.2.

Views and Django Admin call these; none of this logic lives in a view
(CLAUDE.md §2.1, §2.4).
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Role
from apps.core.services import save_record

from .models import Group, GroupTeacher, RoutineSlot, SchoolYear


@transaction.atomic
def save_kindergarten(*, actor, obj, created: bool, request=None):
    return save_record(actor=actor, obj=obj, created=created, request=request)


@transaction.atomic
def save_school_year(*, actor, obj, created: bool, request=None):
    """RFP §3.2.

    Exactly one school year per kindergarten may be current. Enforced here
    rather than by a database constraint because setting a new current year
    has to clear the old one, which is a write, not a check.
    """
    if obj.ends_on <= obj.starts_on:
        raise ValidationError(
            {"ends_on": "Дуусах огноо эхлэх огнооноос хойш байх ёстой."}
        )

    save_record(actor=actor, obj=obj, created=created, request=request)

    if obj.is_current:
        SchoolYear.objects.filter(
            kindergarten=obj.kindergarten, is_current=True
        ).exclude(pk=obj.pk).update(is_current=False)

    if created:
        # RFP §6.4 splits the year into four terms, and Assessment.term is
        # required — a year without terms is a year in which nothing can be
        # assessed. Imported here rather than at module level: assessment
        # already imports children and tenants.
        from apps.assessment.services import ensure_default_terms

        ensure_default_terms(actor=actor, school_year=obj, request=request)

    return obj


@transaction.atomic
def save_group(*, actor, obj, created: bool, request=None):
    """A group's kindergarten must match its school year's.

    Nothing in the schema prevents the mismatch, and if it happened the
    denormalized ``kindergarten_id`` that every tenant filter relies on
    (CLAUDE.md §3.2) would point at the wrong tenant.
    """
    if obj.school_year.kindergarten_id != obj.kindergarten_id:
        raise ValidationError(
            {"school_year": "Хичээлийн жил нь өөр цэцэрлэгийнх байна."}
        )
    return save_record(actor=actor, obj=obj, created=created, request=request)


@transaction.atomic
def assign_teacher(*, actor, group: Group, membership, role=GroupTeacher.Role.PRIMARY,
                   started_on=None, request=None) -> GroupTeacher:
    """RFP §2.1 — assign a teacher to a group.

    This is the record ``can_access_child`` reads for teachers, so the checks
    below are authorization decisions, not data hygiene.
    """
    if membership.role != Role.TEACHER:
        raise ValidationError("Зөвхөн багшийг бүлэгт хуваарилна.")

    if membership.kindergarten_id != group.kindergarten_id:
        raise ValidationError(
            "Багш нь тухайн цэцэрлэгт харьяалагдахгүй байна."
        )

    if not membership.is_active:
        raise ValidationError("Идэвхгүй гишүүнчлэлийг хуваарилах боломжгүй.")

    assignment = GroupTeacher(
        kindergarten_id=group.kindergarten_id,
        group=group,
        teacher_membership=membership,
        role=role,
        started_on=started_on,
    )
    return save_record(actor=actor, obj=assignment, created=True, request=request)


@transaction.atomic
def save_group_teacher(*, actor, obj, created: bool, request=None):
    """Admin entry point. Runs the same checks as :func:`assign_teacher`."""
    if obj.teacher_membership.role != Role.TEACHER:
        raise ValidationError("Зөвхөн багшийг бүлэгт хуваарилна.")

    if obj.teacher_membership.kindergarten_id != obj.group.kindergarten_id:
        raise ValidationError("Багш нь тухайн цэцэрлэгт харьяалагдахгүй байна.")

    obj.kindergarten_id = obj.group.kindergarten_id
    return save_record(actor=actor, obj=obj, created=created, request=request)


@transaction.atomic
def archive_group(*, actor, group: Group, request=None) -> Group:
    """RFP §3.2 — a group is archived, never deleted.

    Enrollments keep pointing at it, which is what preserves a teacher's
    access to the years they taught.
    """
    group.status = Group.Status.ARCHIVED
    return save_record(actor=actor, obj=group, created=False, request=request)


# The routine in the model regulation's own example, as a starting point a
# kindergarten then edits. §7.8.1 makes the durations the group's own
# decision, so these are defaults and never a constraint.
DEFAULT_ROUTINE = [
    ("08:30", "08:50", "Хүүхэд хүлээн авах"),
    ("08:50", "09:10", "Өглөөний дасгал"),
    ("09:30", "10:00", "Өглөөний цай"),
    ("10:10", "11:00", "Хичээл, үйл ажиллагаа"),
    ("11:00", "12:20", "Гадаа тоглолт, зугаалга"),
    ("12:30", "13:10", "Өдрийн хоол"),
    ("13:30", "15:15", "Унтлага"),
    ("15:30", "16:00", "Үдийн цай"),
    ("16:00", "17:30", "Чөлөөт тоглоом, дугуйлан"),
    ("17:30", "18:00", "Хүүхэд гэрт нь тараах"),
]


@transaction.atomic
def save_routine_slot(*, actor, obj, created: bool, request=None):
    """One block of the day — Үлгэрчилсэн дүрэм §7.8.

    The kindergarten follows the group, so nothing else may set it: a block
    filed against the wrong tenant would be invisible to the §3.2 filter
    that every screen relies on.
    """
    obj.kindergarten_id = obj.group.kindergarten_id

    if obj.ends_at <= obj.starts_at:
        raise ValidationError(
            {"ends_at": "Дуусах цаг эхлэх цагаас хойш байх ёстой."}
        )
    if not obj.activity.strip():
        raise ValidationError({"activity": "Үйл ажиллагааны нэрийг оруулна уу."})

    # Overlaps are refused rather than merged: a day where 13:00 belongs to
    # two blocks has no answer to "what is happening now", which is the one
    # question this exists to answer.
    clash = RoutineSlot.objects.filter(
        group=obj.group,
        starts_at__lt=obj.ends_at,
        ends_at__gt=obj.starts_at,
    ).exclude(pk=obj.pk).first()
    if clash is not None:
        raise ValidationError(
            f"Энэ цаг «{clash.activity}» ({clash.starts_at:%H:%M}–"
            f"{clash.ends_at:%H:%M})-тэй давхцаж байна."
        )

    return save_record(actor=actor, obj=obj, created=created, request=request)


@transaction.atomic
def apply_default_routine(*, actor, group, request=None) -> list:
    """Give a group the regulation's example day, once.

    Refuses rather than merges when the group already has a routine: a
    second pass would collide with what the teacher has already adjusted,
    and silently skipping would look like the button did nothing.
    """
    import datetime as dt

    if RoutineSlot.objects.filter(group=group).exists():
        raise ValidationError("Энэ бүлэгт өдрийн дэглэм аль хэдийн бий.")

    created = []
    for starts, ends, activity in DEFAULT_ROUTINE:
        slot = RoutineSlot(
            kindergarten_id=group.kindergarten_id,
            group=group,
            starts_at=dt.time.fromisoformat(starts),
            ends_at=dt.time.fromisoformat(ends),
            activity=activity,
        )
        created.append(save_record(actor=actor, obj=slot, created=True,
                                   request=request))
    return created

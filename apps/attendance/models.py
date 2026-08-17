"""Daily attendance — нэмэлт.md §1.

This is the smallest table in the finance half of the system and the most
consequential. §17 makes it the single source of truth: a day recorded here
is reused by the attendance report, the meal calculation, the state funding
claim and the monthly report, and nowhere is it typed in a second time.

That is also the risk. A wrong observation is a wrong sentence in a
portfolio; a wrong attendance mark becomes a wrong funding claim submitted to
a government body. Three decisions in this file follow from that.

**It hangs off `Enrollment`, not `Child`** (CLAUDE.md §1.2, with money
attached). A child who transfers in January has two enrollments, and their
March attendance belongs to whichever kindergarten they actually attended.
Pointing at `Child` would attribute the whole year to wherever the child is
*now* — which is a funding claim by the wrong institution.

**The status vocabulary is closed, but its funding value is not.** The six
statuses come from §1 and are a fixed system vocabulary, so `TextChoices` is
right (CLAUDE.md §2.3). What each status is *worth* — whether "Хагас өдөр"
counts as a funding day, half a day, or nothing — is a policy that varies by
funding rule and by year. That number is deliberately **not** in this file;
it lives in the funding rule configuration, where an administrator sets it.
Writing it here would hard-code a government formula nobody has confirmed.

**Corrections are visible, not silent.** §14 requires who changed what, from
what, to what. `simple_history` keeps the full row history; the service layer
additionally writes an `AuditLog` entry naming the old and new status.
"""

from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TenantScopedModel


class AttendanceStatus(models.TextChoices):
    """The six states from нэмэлт.md §1.

    A closed vocabulary set by the requirement, not administrator
    configuration — contrast `DevelopmentDomain`, which is a table because a
    kindergarten invents its own. "Бусад" is the escape hatch that keeps a
    teacher from having to force an unusual day into a wrong category.
    """

    PRESENT = "present", "Ирсэн"
    EXCUSED = "excused", "Чөлөөтэй"
    SICK = "sick", "Өвчтэй"
    ABSENT = "absent", "Тасалсан"
    HALF_DAY = "half_day", "Хагас өдөр"
    OTHER = "other", "Бусад"


class Attendance(TenantScopedModel):
    """One child, one day, one status.

    The uniqueness constraint is the point: `(enrollment, date)` may exist at
    most once, so a double-submitted form or a teacher opening the screen
    twice cannot produce two rows for the same day and quietly double a
    funding claim.
    """

    enrollment = models.ForeignKey(
        "children.Enrollment",
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="элсэлт",
    )
    # Denormalized so a child's attendance can be read without joining
    # through Enrollment. The enrollment remains the authority for *which
    # kindergarten* the day belongs to; this is for lookups and display.
    child = models.ForeignKey(
        "children.Child",
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="хүүхэд",
    )
    date = models.DateField("огноо", db_index=True)
    status = models.CharField(
        "төлөв", max_length=20, choices=AttendanceStatus.choices
    )
    note = models.CharField("тайлбар", max_length=300, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "ирц"
        verbose_name_plural = "ирц"
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "date"],
                condition=models.Q(deleted_at__isnull=True),
                name="attendance_one_row_per_enrollment_per_day",
            ),
        ]
        indexes = [
            # The group day sheet: "every child in this group on this date".
            models.Index(fields=["kindergarten", "date"]),
            # The funding and meal calculations: "this child's days in a
            # month", which is always a range scan over one child.
            models.Index(fields=["child", "date"]),
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.child} · {self.date} · {self.get_status_display()}"

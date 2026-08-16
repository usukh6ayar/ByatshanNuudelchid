"""Kindergartens, school years and groups — spec section 6.1."""

from django.db import models

from apps.core.models import BaseModel, TenantScopedModel


class Kindergarten(BaseModel):
    """RFP §3.2. The tenant boundary for the whole system."""

    name = models.CharField("нэр", max_length=200)
    address = models.TextField("хаяг", blank=True)
    phone = models.CharField("утас", max_length=20, blank=True)
    email = models.EmailField("и-мэйл", blank=True)
    description = models.TextField("танилцуулга", blank=True)
    is_active = models.BooleanField("идэвхтэй", default=True)

    # logo / photo become MediaFile FKs in phase 4.

    class Meta:
        verbose_name = "цэцэрлэг"
        verbose_name_plural = "цэцэрлэгүүд"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SchoolYear(BaseModel):
    """RFP §3.2. The dimension that runs through the entire data model."""

    kindergarten = models.ForeignKey(Kindergarten, on_delete=models.PROTECT,
                                     related_name="school_years")
    name = models.CharField("нэр", max_length=20, help_text="ж: 2025-2026")
    starts_on = models.DateField("эхлэх огноо")
    ends_on = models.DateField("дуусах огноо")
    is_current = models.BooleanField("одоогийн", default=False)

    class Meta:
        verbose_name = "хичээлийн жил"
        verbose_name_plural = "хичээлийн жилүүд"
        ordering = ["-starts_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["kindergarten", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_school_year_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kindergarten.name} — {self.name}"


class Group(TenantScopedModel):
    """RFP §3.2.

    A group belongs to a school year: "Sunflower 2025-2026" and
    "Sunflower 2026-2027" are two rows. Staff assignment, class photo and
    group rules all change annually, and §3.2 lists name, age category and
    school year together.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Идэвхтэй"
        ARCHIVED = "archived", "Архивлагдсан"

    class AgeBand(models.TextChoices):
        """The four bands Mongolian kindergartens use, one per year of age.

        Fixed by the national system rather than by any one kindergarten,
        which is why this is ``TextChoices`` and not a table — CLAUDE.md
        §2.3 draws that line at "anything an administrator can edit", and a
        director cannot rename Бэлтгэл бүлэг.

        The ages line up exactly with RFP §4.3's "2, 3, 4, 5 нас тус бүрд
        тусдаа мэдээллийн хуудастай байна", which is what makes a child's
        four age profiles and their four years the same sequence.
        """

        JUNIOR = "junior", "Бага бүлэг"        # 2 нас
        MIDDLE = "middle", "Дунд бүлэг"        # 3 нас
        SENIOR = "senior", "Ахлах бүлэг"       # 4 нас
        PREP = "prep", "Бэлтгэл бүлэг"         # 5 нас

    #: Which year of age each band holds — §4.3's four pages, in order.
    BAND_AGES = {
        AgeBand.JUNIOR: 2,
        AgeBand.MIDDLE: 3,
        AgeBand.SENIOR: 4,
        AgeBand.PREP: 5,
    }

    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT,
                                    related_name="groups")
    name = models.CharField("нэр", max_length=100)
    age_band = models.CharField(
        "насны бүлэг", max_length=10, choices=AgeBand.choices, blank=True,
        help_text="Бага (2 нас), Дунд (3), Ахлах (4), Бэлтгэл (5)",
    )
    # Kept alongside the band: §3.2 asks for "бүлгийн насны ангилал" and a
    # kindergarten often writes its own ("3-4 нас", "холимог"), which the
    # four national bands cannot express.
    age_category = models.CharField("насны ангилал", max_length=50, blank=True)
    timetable = models.TextField("хичээлийн хуваарь", blank=True)
    rules = models.TextField("бүлгийн дүрэм", blank=True)
    status = models.CharField("төлөв", max_length=20,
                              choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name = "бүлэг"
        verbose_name_plural = "бүлгүүд"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_group_name_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["kindergarten", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_year.name})"


class GroupTeacher(TenantScopedModel):
    """Teacher assignment — RFP §2.1 "assign a teacher to a group".

    This table is what ``can_access_child`` reads for teachers. Because
    assignments are historical rather than overwritten, a teacher keeps
    access to the records they wrote in previous years.
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Үндсэн багш"
        ASSISTANT = "assistant", "Туслах багш"

    group = models.ForeignKey(Group, on_delete=models.CASCADE,
                              related_name="teacher_assignments")
    teacher_membership = models.ForeignKey(
        "accounts.Membership", on_delete=models.CASCADE,
        related_name="group_assignments",
    )
    role = models.CharField("үүрэг", max_length=20,
                            choices=Role.choices, default=Role.PRIMARY)
    started_on = models.DateField("эхэлсэн огноо", null=True, blank=True)
    ended_on = models.DateField("дууссан огноо", null=True, blank=True)

    class Meta:
        verbose_name = "бүлгийн багш"
        verbose_name_plural = "бүлгийн багш нар"
        indexes = [
            models.Index(fields=["group", "teacher_membership"]),
        ]

    def __str__(self) -> str:
        return f"{self.teacher_membership.user} — {self.group}"

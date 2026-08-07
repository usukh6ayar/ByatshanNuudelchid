"""Children, guardianships and enrollments — spec section 6.1."""

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TenantScopedModel


class Child(TenantScopedModel):
    """RFP §3.4.

    Note there is no ``group`` field. A child's group membership for a given
    year lives in ``Enrollment``. ``kindergarten`` here means "currently
    attending" and exists for listing and filtering only — it is never an
    input to an authorization decision (CLAUDE.md §1.2).
    """

    class Sex(models.TextChoices):
        MALE = "male", "Эрэгтэй"
        FEMALE = "female", "Эмэгтэй"

    class Status(models.TextChoices):
        ACTIVE = "active", "Идэвхтэй"
        TRANSFERRED = "transferred", "Шилжсэн"
        GRADUATED = "graduated", "Төгссөн"
        ARCHIVED = "archived", "Архивлагдсан"

    last_name = models.CharField("овог", max_length=100)
    first_name = models.CharField("нэр", max_length=100)
    national_id = models.CharField(
        "регистр / дотоод код", max_length=32,
        help_text="Давхцахгүй байх ёстой",
    )
    sex = models.CharField("хүйс", max_length=10, choices=Sex.choices)
    date_of_birth = models.DateField("төрсөн огноо")

    enrolled_on = models.DateField("элссэн огноо", null=True, blank=True)
    left_on = models.DateField("гарсан огноо", null=True, blank=True)

    health_notes = models.TextField(
        "эрүүл мэндийн товч тэмдэглэл", blank=True,
        help_text="Анхаарах шаардлагатай мэдээлэл",
    )
    status = models.CharField("төлөв", max_length=20,
                              choices=Status.choices, default=Status.ACTIVE)

    history = HistoricalRecords()   # RFP §4.1

    class Meta:
        verbose_name = "хүүхэд"
        verbose_name_plural = "хүүхдүүд"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kindergarten", "national_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_child_national_id",
            ),
        ]
        indexes = [
            # Driven by the §11 filters — spec section 10.2
            models.Index(fields=["kindergarten", "status"]),
            models.Index(fields=["kindergarten", "date_of_birth"]),
            models.Index(fields=["kindergarten", "sex"]),
            models.Index(fields=["kindergarten", "last_name", "first_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.last_name} {self.first_name}"

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"


class Guardianship(TenantScopedModel):
    """Child ↔ guardian, many-to-many — RFP §3.5.

    One child may have several guardians; one guardian may have several
    children, including at different kindergartens.
    """

    class Relation(models.TextChoices):
        MOTHER = "mother", "Ээж"
        FATHER = "father", "Аав"
        GRANDPARENT = "grandparent", "Өвөө, эмээ"
        OTHER = "other", "Бусад"

    child = models.ForeignKey(Child, on_delete=models.CASCADE,
                              related_name="guardianships")
    guardian_user = models.ForeignKey(settings.AUTH_USER_MODEL,
                                      on_delete=models.CASCADE,
                                      related_name="guardianships")
    relation = models.CharField("хамаарал", max_length=20,
                                choices=Relation.choices)
    is_primary = models.BooleanField("үндсэн асран хамгаалагч", default=False)
    can_view = models.BooleanField(
        "мэдээлэл харах эрхтэй", default=True,
        help_text="Гэр бүлийн эрх зүйн шийдвэрээр хязгаарлагдсан тохиолдолд",
    )

    class Meta:
        verbose_name = "асран хамгаалагч"
        verbose_name_plural = "асран хамгаалагчид"
        constraints = [
            models.UniqueConstraint(
                fields=["child", "guardian_user"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_guardianship",
            ),
        ]
        indexes = [
            models.Index(fields=["guardian_user", "can_view"]),
            models.Index(fields=["child"]),
        ]

    def __str__(self) -> str:
        return f"{self.guardian_user} — {self.child} ({self.get_relation_display()})"


class Enrollment(TenantScopedModel):
    """The keystone table — spec section 6.1.

    A child stays in the system for three to four years and changes group
    each year. Storing that as history rather than a column on ``Child``
    is what makes transfers, year-over-year comparison, per-age pages and
    historical teacher access all work.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Идэвхтэй"
        TRANSFERRED = "transferred", "Шилжсэн"
        GRADUATED = "graduated", "Төгссөн"
        ARCHIVED = "archived", "Архивлагдсан"

    child = models.ForeignKey(Child, on_delete=models.CASCADE,
                              related_name="enrollments")
    group = models.ForeignKey("tenants.Group", on_delete=models.PROTECT,
                              related_name="enrollments")
    school_year = models.ForeignKey("tenants.SchoolYear",
                                    on_delete=models.PROTECT,
                                    related_name="enrollments")
    started_on = models.DateField("элссэн огноо")
    ended_on = models.DateField("дууссан огноо", null=True, blank=True)
    status = models.CharField("төлөв", max_length=20,
                              choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name = "бүртгэл"
        verbose_name_plural = "бүртгэлүүд"
        ordering = ["-started_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "school_year"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_enrollment_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["school_year", "status"]),
            models.Index(fields=["child", "school_year"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.group}"

    @property
    def age_at_start(self) -> int:
        """The child's age when this enrollment began.

        Used by the per-age portfolio pages (RFP §4.3).
        """
        dob, start = self.child.date_of_birth, self.started_on
        return start.year - dob.year - ((start.month, start.day) < (dob.month, dob.day))

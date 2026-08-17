"""Teacher and parent observations — RFP §5.1, §5.2, §5.4. Spec section 6.3.

Phase 1 records the observation itself. The evidence photos and attachments
of §5.1, and the §5.3 side-by-side comparison of a child's work over time,
both need ``MediaFile`` and arrive on Day 7 with upload (ROADMAP section 10).
"""

from django.conf import settings
from django.db import models

from apps.assessment.models import AssessmentLevel, DevelopmentDomain
from apps.core.models import BaseModel, TenantScopedModel


class ObservationType(BaseModel):
    """RFP §5.2 — the four starting types, extensible by an administrator.

    Same shape as ``DevelopmentDomain``: ``kindergarten = NULL`` is a system
    default shared by everyone, a row with a kindergarten belongs to that one
    alone, and every read goes through ``selectors.types_for()``.
    """

    kindergarten = models.ForeignKey(
        "tenants.Kindergarten",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="цэцэрлэг",
        help_text="Хоосон бол системийн үндсэн жагсаалт",
    )
    name = models.CharField("нэр", max_length=100)
    code = models.SlugField("код", max_length=50)
    order = models.PositiveSmallIntegerField("эрэмбэ", default=0)
    is_active = models.BooleanField("идэвхтэй", default=True)

    class Meta:
        verbose_name = "ажиглалтын төрөл"
        verbose_name_plural = "ажиглалтын төрлүүд"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(kindergarten__isnull=True,
                                   deleted_at__isnull=True),
                name="uniq_obs_type_system_code",
            ),
            models.UniqueConstraint(
                fields=["kindergarten", "code"],
                condition=models.Q(kindergarten__isnull=False,
                                   deleted_at__isnull=True),
                name="uniq_obs_type_kindergarten_code",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Observation(TenantScopedModel):
    """RFP §5.1 — what a teacher saw, in the teacher's own words.

    Carries ``enrollment`` as well as ``child`` (spec section 4.2): the
    enrollment fixes which kindergarten and school year the record belongs
    to, which is what keeps it visible to its author after a transfer and
    invisible to the new kindergarten's staff.
    """

    class Source(models.TextChoices):
        """§5.4 — "хэн мэдээлэл оруулсныг ялгаж харуулах"."""

        TEACHER = "teacher", "Багш"
        PARENT = "parent", "Эцэг эх"

    class ReviewStatus(models.TextChoices):
        """§5.4 — the teacher reviews what a parent submits.

        A teacher's own observation is approved on save; there is nobody
        above them to approve it.
        """

        PENDING = "pending", "Хүлээгдэж буй"
        APPROVED = "approved", "Баталсан"
        REVISION_REQUESTED = "revision_requested", "Засвар хүссэн"

    child = models.ForeignKey("children.Child", on_delete=models.CASCADE,
                              related_name="observations")
    enrollment = models.ForeignKey("children.Enrollment",
                                   on_delete=models.PROTECT,
                                   related_name="observations")
    type = models.ForeignKey(ObservationType, on_delete=models.PROTECT,
                             related_name="observations",
                             verbose_name="ажиглалтын төрөл")

    source = models.CharField("оруулсан", max_length=10,
                              choices=Source.choices, default=Source.TEACHER)
    observed_on = models.DateField("ажиглалтын огноо")

    activity_name = models.CharField("үйл ажиллагааны нэр", max_length=200,
                                     blank=True)
    situation = models.TextField("нөхцөл байдал", blank=True)
    child_did = models.TextField("хүүхдийн хийсэн үйлдэл", blank=True)
    child_said = models.TextField("хүүхдийн хэлсэн үг", blank=True)
    teacher_comment = models.TextField("багшийн тайлбар", blank=True)
    next_steps = models.TextField("дараагийн дэмжлэг, төлөвлөгөө", blank=True)

    # §5.1 — "эцэг эхэд харагдах эсэх".
    #
    # Closed by default (product decision, 2026-08-16). This read `default=True`
    # until then, on the reasoning that a hidden observation is the exception.
    # The client's decision is the opposite one: a teacher's note is a working
    # record until they choose to publish it, and a draft thought about a
    # child should not reach the family because someone forgot to untick a
    # box. §5.1 names the field but does not fix its default, so this is a
    # product call rather than a change to the requirement.
    #
    # A family's *own* submission is the exception and is not governed by
    # this default — see ``services.create_observation``.
    visible_to_parents = models.BooleanField("эцэг эхэд харагдах", default=False)
    # §5.4 — "хүүхдийн нэгдсэн тайланд оруулах эсэхийг шийдэх".
    include_in_report = models.BooleanField("тайланд оруулах", default=True)

    review_status = models.CharField("төлөв", max_length=20,
                                     choices=ReviewStatus.choices,
                                     default=ReviewStatus.APPROVED)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reviewed_at = models.DateTimeField("хянасан огноо", null=True, blank=True)
    review_note = models.TextField("хяналтын тэмдэглэл", blank=True)

    class Meta:
        verbose_name = "ажиглалт"
        verbose_name_plural = "ажиглалтууд"
        ordering = ["-observed_on", "-created_at"]
        indexes = [
            # §11's filters and §12.1's "latest observations" tile.
            models.Index(fields=["child", "-observed_on"]),
            models.Index(fields=["kindergarten", "-observed_on"]),
            models.Index(fields=["enrollment", "-observed_on"]),
            models.Index(fields=["source", "review_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.observed_on:%Y.%m.%d}"

    @property
    def summary(self) -> str:
        """The first line a list shows."""
        text = self.activity_name or self.situation or self.child_did
        return text[:120] if text else "(тайлбаргүй)"


class ObservationDomain(TenantScopedModel):
    """Which development domains one observation touches — spec section 6.3.

    Its own table rather than a column: "built a tower and explained it to a
    friend" is creativity, language and communication at once, and a single
    column would make §12.3's per-domain averages wrong.

    ``level`` is optional — §5.1 lists үнэлгээ among the observation's
    fields, but an observation is often just a note with no judgement
    attached.
    """

    observation = models.ForeignKey(Observation, on_delete=models.CASCADE,
                                    related_name="domain_links")
    domain = models.ForeignKey(DevelopmentDomain, on_delete=models.PROTECT,
                               related_name="+",
                               verbose_name="хөгжлийн чиглэл")
    level = models.ForeignKey(AssessmentLevel, null=True, blank=True,
                              on_delete=models.PROTECT, related_name="+",
                              verbose_name="үнэлгээ")

    class Meta:
        verbose_name = "ажиглалтын чиглэл"
        verbose_name_plural = "ажиглалтын чиглэлүүд"
        constraints = [
            models.UniqueConstraint(
                fields=["observation", "domain"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_domain_per_observation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.observation} — {self.domain.name}"

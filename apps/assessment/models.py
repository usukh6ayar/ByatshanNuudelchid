"""Development assessment — RFP §6.1, §6.2, §6.3, §6.4. Spec section 6.4.

Phase 1 covers the configuration tables, the four terms of a school year, the
per-domain assessment, and ``TermReport`` — §6.4's narrative report, pulled
forward from Phase 2 because §20-II lists it as mandatory MVP and §21.7 makes
it an acceptance criterion. ``AnnualReport`` (§6.5) is still Phase 2 — see
ROADMAP section 8.

**Where the configuration lives.** §6.1 and §6.2 require an administrator to
be able to edit the domains and the levels, so both are tables rather than
``TextChoices`` (CLAUDE.md §2.3). ``kindergarten = NULL`` means "system
default, shared by every kindergarten"; a row with a kindergarten belongs to
that one alone. Nothing reads these tables directly — every caller goes
through ``selectors.domains_for()`` / ``selectors.levels_for()``, so the
"system OR mine" condition is written once instead of in every screen.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TenantScopedModel


class ConfigurableModel(BaseModel):
    """Shared shape of the administrator-editable lists — §6.1, §6.2, §5.2.

    ``kindergarten`` is nullable, which ``TenantScopedModel`` does not allow,
    so these inherit ``BaseModel`` and carry their own column (CLAUDE.md §3.1
    anticipates the split).
    """

    kindergarten = models.ForeignKey(
        "tenants.Kindergarten",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="цэцэрлэг",
        help_text="Хоосон бол системийн үндсэн жагсаалт — бүх цэцэрлэгт нийтлэг",
    )
    name = models.CharField("нэр", max_length=100)
    code = models.SlugField(
        "код", max_length=50,
        help_text="Системийн доторх тогтмол нэр. Тайланд харагдахгүй.",
    )
    order = models.PositiveSmallIntegerField("эрэмбэ", default=0)
    is_active = models.BooleanField("идэвхтэй", default=True)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_system_default(self) -> bool:
        return self.kindergarten_id is None


def _code_constraints(model: str) -> list:
    """Unique code, once for the system rows and once per kindergarten.

    Two constraints rather than one on ``(kindergarten, code)``: PostgreSQL
    treats NULLs as distinct in a unique index, so the single version would
    let the system list hold nine rows all coded ``language``.
    """
    return [
        models.UniqueConstraint(
            fields=["code"],
            condition=models.Q(kindergarten__isnull=True, deleted_at__isnull=True),
            name=f"uniq_{model}_system_code",
        ),
        models.UniqueConstraint(
            fields=["kindergarten", "code"],
            condition=models.Q(kindergarten__isnull=False, deleted_at__isnull=True),
            name=f"uniq_{model}_kindergarten_code",
        ),
    ]


class DevelopmentDomain(ConfigurableModel):
    """RFP §6.1 — бие бялдар, хэл яриа, танин мэдэхүй and the rest.

    The nine examples in §6.1 ship as system defaults in migration 0002.
    """

    color = models.CharField(
        "өнгө", max_length=7, default="#6366f1",
        help_text="Графикт хэрэглэх өнгө, ж: #6366f1",
    )
    description = models.TextField("тайлбар", blank=True)

    class Meta(ConfigurableModel.Meta):
        verbose_name = "хөгжлийн чиглэл"
        verbose_name_plural = "хөгжлийн чиглэлүүд"
        constraints = _code_constraints("domain")


class DevelopmentIndicator(BaseModel):
    """A finer criterion inside a domain — §6.1.

    Deliberately unused in Phase 1: assessment happens at the domain level
    (§6.4, §6.5 and §12.3 all aggregate per domain). The table and the
    nullable ``Assessment.indicator`` column exist now so that criteria can
    be added later without migrating assessment rows that already exist.
    """

    domain = models.ForeignKey(DevelopmentDomain, on_delete=models.CASCADE,
                               related_name="indicators")
    name = models.CharField("нэр", max_length=200)
    age_from = models.PositiveSmallIntegerField("хамрах нас (эхлэх)", default=2)
    age_to = models.PositiveSmallIntegerField("хамрах нас (дуусах)", default=5)
    order = models.PositiveSmallIntegerField("эрэмбэ", default=0)
    is_active = models.BooleanField("идэвхтэй", default=True)

    class Meta:
        verbose_name = "хөгжлийн шалгуур"
        verbose_name_plural = "хөгжлийн шалгуурууд"
        ordering = ["domain", "order", "name"]

    def __str__(self) -> str:
        return f"{self.domain.name} — {self.name}"


class AssessmentScale(BaseModel):
    """RFP §6.2 — the set of levels used when assessing.

    A scale rather than four fixed levels because §6.2 lets an administrator
    rename them, recolour them and describe them.
    """

    kindergarten = models.ForeignKey(
        "tenants.Kindergarten",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="цэцэрлэг",
        help_text="Хоосон бол системийн үндсэн шат",
    )
    name = models.CharField("нэр", max_length=100)
    is_default = models.BooleanField(
        "үндсэн шат", default=False,
        help_text="Шинэ үнэлгээнд сонгогдох шат",
    )

    class Meta:
        verbose_name = "үнэлгээний шат"
        verbose_name_plural = "үнэлгээний шатууд"
        ordering = ["kindergarten__name", "name"]

    def __str__(self) -> str:
        return self.name


class AssessmentLevel(BaseModel):
    """One step of a scale — RFP §6.2's 1–4.

    ``value`` is what §12.3's per-domain average and the Phase 3 radar chart
    are computed from, so it stays numeric even when the label is renamed.
    """

    scale = models.ForeignKey(AssessmentScale, on_delete=models.CASCADE,
                              related_name="levels")
    value = models.PositiveSmallIntegerField(
        "утга", validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    label = models.CharField("нэр", max_length=100)
    color = models.CharField("өнгө", max_length=7, default="#94a3b8")
    description = models.TextField("тайлбар", blank=True)

    class Meta:
        verbose_name = "үнэлгээний түвшин"
        verbose_name_plural = "үнэлгээний түвшнүүд"
        ordering = ["scale", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["scale", "value"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_level_value_per_scale",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.value}. {self.label}"


class Term(TenantScopedModel):
    """RFP §6.4 — "хичээлийн жилийг дөрвөн улиралд хуваана".

    Belongs to a school year, which already identifies the kindergarten.
    ``kindergarten`` is carried anyway because CLAUDE.md §3.2 requires it on
    every tenant-scoped table even when a relation would reach it: one
    filter then enforces the §3.2 isolation instead of a join that someone
    eventually forgets. ``save_term`` keeps the two in step.
    """

    school_year = models.ForeignKey("tenants.SchoolYear",
                                    on_delete=models.CASCADE,
                                    related_name="terms")
    number = models.PositiveSmallIntegerField(
        "улирал", validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    name = models.CharField("нэр", max_length=50)
    starts_on = models.DateField("эхлэх огноо")
    ends_on = models.DateField("дуусах огноо")

    class Meta:
        verbose_name = "улирал"
        verbose_name_plural = "улирлууд"
        ordering = ["school_year", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "number"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_term_number_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["school_year", "starts_on", "ends_on"]),
        ]

    def __str__(self) -> str:
        return f"{self.school_year.name} — {self.name}"

    def covers(self, on) -> bool:
        return self.starts_on <= on <= self.ends_on


class Assessment(TenantScopedModel):
    """One domain, one term, one child — RFP §6.3, §6.4.

    ``unique(child, enrollment, domain, term)`` is §17's "a double-click must
    not save the same record twice", enforced by the database rather than by
    the application. The quick-assessment grid (§6.3) posts a whole group at
    once, which is exactly where a duplicate submission happens.

    ``indicator`` stays NULL in Phase 1 and is deliberately left out of the
    constraint: PostgreSQL treats NULLs as distinct, so including it would
    make the constraint match nothing and silently permit the duplicates it
    exists to prevent.
    """

    child = models.ForeignKey("children.Child", on_delete=models.CASCADE,
                              related_name="assessments")
    enrollment = models.ForeignKey("children.Enrollment",
                                   on_delete=models.PROTECT,
                                   related_name="assessments")
    domain = models.ForeignKey(DevelopmentDomain, on_delete=models.PROTECT,
                               related_name="assessments",
                               verbose_name="хөгжлийн чиглэл")
    indicator = models.ForeignKey(DevelopmentIndicator, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+")
    term = models.ForeignKey(Term, on_delete=models.PROTECT,
                             related_name="assessments", verbose_name="улирал")
    level = models.ForeignKey(AssessmentLevel, on_delete=models.PROTECT,
                              related_name="+", verbose_name="үнэлгээ")
    comment = models.TextField("тайлбар", blank=True)

    # RFP §2.3 — a guardian sees "багшийн зөвшөөрсөн ажиглалт, үнэлгээ".
    # §6.3's quick assessment is a working draft a teacher fills in over
    # several sittings, so the default is closed and the teacher opens the
    # term when it is finished. §6.4's narrative term report, which carries
    # its own draft/final status, is Phase 2.
    visible_to_parents = models.BooleanField("эцэг эхэд харагдах", default=False)

    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    # Not auto_now: §6.4 wants the date the judgement was made, and every
    # other write touches this row too — opening the term to the guardians
    # would otherwise restamp it as if the child had just been reassessed.
    # ``save_assessment`` sets it when the level or comment actually changes.
    assessed_at = models.DateTimeField("үнэлсэн огноо", auto_now_add=True)

    class Meta:
        verbose_name = "хөгжлийн үнэлгээ"
        verbose_name_plural = "хөгжлийн үнэлгээ"
        ordering = ["-term__number", "domain__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "enrollment", "domain", "term"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_assessment_per_domain_term",
            ),
        ]
        indexes = [
            models.Index(fields=["child", "term"]),
            models.Index(fields=["kindergarten", "term"]),
            models.Index(fields=["enrollment", "term"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.domain.name} ({self.term.name})"


class TermReport(TenantScopedModel):
    """RFP §6.4's narrative report — one per child per term.

    The per-domain levels live in ``Assessment``; this is the wrapper a
    teacher writes once the term's grid is filled in. There is deliberately
    no general ``teacher_comment`` here: ``Assessment.comment`` already
    holds the teacher's note for each domain, and the approved mockup shows
    it there, under the domain it belongs to. A second comment box would
    leave the teacher guessing which one the family reads.

    ``enrollment`` is part of the uniqueness constraint for the same reason
    ``Assessment`` carries it: after a transfer the previous kindergarten's
    report stays attached to the enrollment it was written under, so
    ``visible_kindergartens()`` keeps showing it to its author and to nobody
    else (CLAUDE.md §1.2).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Ноорог"
        FINAL = "final", "Дууссан"

    child = models.ForeignKey("children.Child", on_delete=models.CASCADE,
                              related_name="term_reports")
    enrollment = models.ForeignKey("children.Enrollment",
                                   on_delete=models.PROTECT,
                                   related_name="term_reports")
    term = models.ForeignKey(Term, on_delete=models.PROTECT,
                             related_name="reports", verbose_name="улирал")

    strengths = models.TextField("давуу тал", blank=True)
    needs_support = models.TextField("дэмжих шаардлагатай чадвар", blank=True)
    next_goals = models.TextField("дараагийн улирлын зорилго", blank=True)
    advice_for_parents = models.TextField("эцэг эхэд өгөх зөвлөмж", blank=True)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                               blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    status = models.CharField("төлөв", max_length=10, choices=Status.choices,
                              default=Status.DRAFT, db_index=True)
    # Not auto_now: §6.4 wants "тайлан үүсгэсэн огноо", the moment the
    # teacher declared it done. ``updated_at`` moves on every save and would
    # report a typo fix as a freshly written report.
    finalized_at = models.DateTimeField("дуусгасан огноо", null=True,
                                        blank=True)

    class Meta:
        verbose_name = "улирлын тайлан"
        verbose_name_plural = "улирлын тайлан"
        ordering = ["-term__number"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "enrollment", "term"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_term_report_per_child_term",
            ),
        ]
        indexes = [
            models.Index(fields=["child", "term"]),
            models.Index(fields=["kindergarten", "term"]),
            models.Index(fields=["enrollment", "term"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.term.name}"

    @property
    def is_final(self) -> bool:
        return self.status == self.Status.FINAL

    @property
    def is_empty(self) -> bool:
        """No narrative at all. ``finalize_term`` refuses to publish this."""
        return not any((self.strengths, self.needs_support,
                        self.next_goals, self.advice_for_parents))

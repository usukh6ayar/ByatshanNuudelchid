"""Users and memberships — spec section 4.1.

Permissions are never stored on the user. They live on ``Membership``,
so one person can hold several roles across several kindergartens:
a teacher whose own child attends the same kindergarten, a teacher working
at two sites, a guardian with children at two kindergartens.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Role(models.TextChoices):
    """System-level values, so a TextChoices enum is appropriate here.

    Contrast with development domains or assessment levels, which the
    administrator edits and therefore live in tables — CLAUDE.md §2.3.
    """

    SUPERADMIN = "superadmin", "Системийн администратор"
    ADMIN = "admin", "Цэцэрлэгийн администратор"
    TEACHER = "teacher", "Багш"
    GUARDIAN = "guardian", "Эцэг эх, асран хамгаалагч"


class UserManager(BaseUserManager):
    def create_user(self, password=None, **fields):
        if not any(fields.get(f) for f in ("username", "email", "phone")):
            raise ValueError(
                "A user needs at least one identifier: username, email or phone."
            )
        if fields.get("email"):
            fields["email"] = self.normalize_email(fields["email"])
        user = self.model(**fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, password=None, **fields):
        fields.setdefault("is_staff", True)
        fields.setdefault("is_superuser", True)
        return self.create_user(password=password, **fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Credentials only. No role field — see ``Membership``.

    RFP §3.1: teachers log in with a username or email, guardians with a
    phone number or email. That is one login form resolving three identifier
    types, not three separate login systems.
    """

    username = models.CharField(
        "хэрэглэгчийн нэр", max_length=150,
        null=True, blank=True, unique=True,
    )
    email = models.EmailField("и-мэйл", null=True, blank=True, unique=True)
    phone = models.CharField("утас", max_length=20, null=True, blank=True, unique=True)

    last_name = models.CharField("овог", max_length=100, blank=True)
    first_name = models.CharField("нэр", max_length=100, blank=True)
    # NOTE: `avatar` is added as a MediaFile FK in phase 4, once the media
    # pipeline exists. It is not stubbed here — an unused column would only
    # invite someone to store a raw path in it.

    is_active = models.BooleanField("идэвхтэй", default=True)
    is_staff = models.BooleanField("Django admin хандах", default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "хэрэглэгч"
        verbose_name_plural = "хэрэглэгчид"

    def __str__(self) -> str:
        full = f"{self.last_name} {self.first_name}".strip()
        return full or self.username or self.email or self.phone or f"User #{self.pk}"

    # ---------------------------------------------------------------- helpers
    # These exist so permission code reads clearly. The authorization
    # decisions themselves live in apps/core/permissions.py — CLAUDE.md §1.1.

    @property
    def kindergarten_ids(self) -> set[int]:
        """Kindergartens where this user holds an active membership."""
        return set(
            self.memberships.filter(
                is_active=True, kindergarten__isnull=False
            ).values_list("kindergarten_id", flat=True)
        )

    def has_membership_in(self, kindergarten_ids, roles=None) -> bool:
        """True if an active membership exists in any of ``kindergarten_ids``.

        A ``superadmin`` membership has ``kindergarten=None`` and therefore
        matches every kindergarten.
        """
        qs = self.memberships.filter(is_active=True)
        if roles is not None:
            qs = qs.filter(role__in=roles)

        if qs.filter(role=Role.SUPERADMIN).exists():
            return True

        if not kindergarten_ids:
            return False
        return qs.filter(kindergarten_id__in=kindergarten_ids).exists()


class Membership(BaseModel):
    """The unit of authorization — spec section 4.1.

    ``kindergarten`` is null only for ``superadmin``, whose scope is the
    whole system (registering kindergartens, backups, all users).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name="memberships")
    kindergarten = models.ForeignKey(
        "tenants.Kindergarten", null=True, blank=True,
        on_delete=models.CASCADE, related_name="memberships",
    )
    role = models.CharField("эрх", max_length=20, choices=Role.choices)
    is_active = models.BooleanField("идэвхтэй", default=True)
    started_on = models.DateField("эхэлсэн огноо", null=True, blank=True)

    class Meta:
        verbose_name = "гишүүнчлэл"
        verbose_name_plural = "гишүүнчлэлүүд"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kindergarten", "role"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_active_membership",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role="superadmin", kindergarten__isnull=True)
                    | ~models.Q(role="superadmin") & models.Q(kindergarten__isnull=False)
                ),
                name="superadmin_is_system_wide",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["kindergarten", "role", "is_active"]),
        ]

    def __str__(self) -> str:
        where = self.kindergarten or "систем"
        return f"{self.user} — {self.get_role_display()} @ {where}"


class TeacherProfile(BaseModel):
    """RFP §3.3."""

    user = models.OneToOneField(User, on_delete=models.CASCADE,
                                related_name="teacher_profile")
    specialization = models.CharField("мэргэжил", max_length=200, blank=True)
    years_of_service = models.PositiveSmallIntegerField("ажилласан жил", null=True,
                                                        blank=True)
    education = models.TextField("боловсрол", blank=True)
    bio = models.TextField("өөрийн тухай", blank=True)
    is_employed = models.BooleanField("ажиллаж байгаа", default=True)

    class Meta:
        verbose_name = "багшийн профайл"
        verbose_name_plural = "багшийн профайлууд"


class GuardianProfile(BaseModel):
    """RFP §3.5."""

    user = models.OneToOneField(User, on_delete=models.CASCADE,
                                related_name="guardian_profile")
    note = models.TextField("тэмдэглэл", blank=True)

    class Meta:
        verbose_name = "эцэг эхийн профайл"
        verbose_name_plural = "эцэг эхийн профайлууд"

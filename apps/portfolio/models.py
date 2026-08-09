"""Child portfolio — RFP §4.1, §4.2, §4.3. Phase 1.

Milestones and photo albums (§4.4, §4.5) are Phase 2; see spec section 6.2.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TenantScopedModel


class AboutMe(TenantScopedModel):
    """RFP §4.1 — "Миний тухай".

    One row per child, edited by the guardian (§2.3 lists this as a parent
    capability) and by the teacher. ``django-simple-history`` records who
    changed what, which §4.1 requires.
    """

    child = models.OneToOneField(
        "children.Child", on_delete=models.CASCADE, related_name="about_me"
    )

    introduction = models.TextField("танилцуулга", blank=True)
    name_meaning = models.TextField("нэрний утга", blank=True)
    memorable_sayings = models.TextField("миний хэлсэн сонирхолтой үг", blank=True)
    dream = models.TextField("миний мөрөөдөл", blank=True)
    distinguishing_traits = models.TextField("миний онцлог", blank=True)

    height_cm = models.DecimalField(
        "миний өндөр (см)", max_digits=5, decimal_places=1,
        null=True, blank=True,
        validators=[MinValueValidator(30), MaxValueValidator(200)],
    )
    weight_kg = models.DecimalField(
        "миний жин (кг)", max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(2), MaxValueValidator(100)],
    )
    recorded_on = models.DateField("бүртгэсэн огноо", null=True, blank=True)

    # first_signature and additional photos become MediaFile links on Day 7.

    history = HistoricalRecords()

    class Meta:
        verbose_name = "миний тухай"
        verbose_name_plural = "миний тухай"

    def __str__(self) -> str:
        return f"Миний тухай — {self.child}"


class ChildAgeProfile(TenantScopedModel):
    """RFP §4.3 — one page per age, from 2 to 5.

    Seventeen typed columns rather than a name/value table: §917's group
    analytics ("every child's favourite colour") turn into awkward pivots
    under EAV, and reports and exports both want columns.
    """

    class Age(models.IntegerChoices):
        TWO = 2, "2 нас"
        THREE = 3, "3 нас"
        FOUR = 4, "4 нас"
        FIVE = 5, "5 нас"

    child = models.ForeignKey(
        "children.Child", on_delete=models.CASCADE, related_name="age_profiles"
    )
    age = models.PositiveSmallIntegerField("нас", choices=Age.choices)
    school_year = models.ForeignKey(
        "tenants.SchoolYear", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    favorite_color = models.CharField("дуртай өнгө", max_length=100, blank=True)
    favorite_food = models.CharField("дуртай хоол", max_length=200, blank=True)
    favorite_toy = models.CharField("дуртай тоглоом", max_length=200, blank=True)
    favorite_book = models.CharField("дуртай ном", max_length=200, blank=True)
    favorite_song = models.CharField("дуртай дуу", max_length=200, blank=True)
    favorite_story = models.CharField("дуртай үлгэр", max_length=200, blank=True)
    favorite_movie = models.CharField("дуртай кино", max_length=200, blank=True)
    favorite_clothes = models.CharField("дуртай хувцас", max_length=200, blank=True)
    favorite_activity = models.CharField(
        "дуртай үйл ажиллагаа", max_length=200, blank=True
    )

    personality = models.TextField("зан чанар", blank=True)
    emotional_traits = models.TextField("сэтгэл хөдлөлийн онцлог", blank=True)
    family_members = models.TextField("гэр бүлийн гишүүд", blank=True)
    learning_interest = models.TextField("суралцах сонирхол", blank=True)
    new_skills = models.TextField("шинээр эзэмшсэн чадвар", blank=True)

    # §4.3 keeps the two voices apart, and so does the service layer: a
    # guardian may only write parent_note, a teacher only teacher_note.
    parent_note = models.TextField("эцэг эхийн тэмдэглэл", blank=True)
    teacher_note = models.TextField("багшийн тэмдэглэл", blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "насны хуудас"
        verbose_name_plural = "насны хуудсууд"
        ordering = ["age"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "age"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_age_profile_per_child",
            ),
        ]
        indexes = [
            models.Index(fields=["child", "age"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.get_age_display()}"


class BirthdayNote(TenantScopedModel):
    """RFP §4.2 — a note for each birthday.

    The zodiac sign and year animal are computed from the date of birth
    (§206), not stored — see ``apps/portfolio/zodiac.py``.
    """

    child = models.ForeignKey(
        "children.Child", on_delete=models.CASCADE, related_name="birthday_notes"
    )
    age = models.PositiveSmallIntegerField(
        "хэдэн насны төрсөн өдөр",
        validators=[MinValueValidator(0), MaxValueValidator(18)],
    )
    note = models.TextField("тэмдэглэл", blank=True)

    class Meta:
        verbose_name = "төрсөн өдрийн тэмдэглэл"
        verbose_name_plural = "төрсөн өдрийн тэмдэглэлүүд"
        ordering = ["age"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "age"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_birthday_note_per_age",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.age} нас"

"""The system-default configuration — RFP §5.2, §6.1, §6.2.

``Assessment.domain``, ``Assessment.level`` and ``Observation.type`` are all
required columns, so an installation without these rows is one where nothing
can be recorded at all. They are therefore not optional sample data: they
are part of a working system.

Defined here rather than inside the migrations because two callers need
them:

* the data migrations, which install them on first migrate;
* the test suite, because ``django_db(transaction=True)`` flushes every
  table at teardown and takes migration-created rows with it. Any test that
  ran after one of those would otherwise find an empty configuration, and
  which tests those are depends on collection order.

``install`` takes the model classes as arguments so a migration can pass its
historical models and the test fixture can pass the real ones. It is
idempotent: every write is a ``get_or_create`` keyed on ``code``, so a
kindergarten that renamed a domain does not get it renamed back.
"""

DOMAINS = [
    ("physical", "Бие бялдар, хөдөлгөөн", "#ef4444"),
    ("language", "Хэл яриа", "#f59e0b"),
    ("cognitive", "Танин мэдэхүй", "#3b82f6"),
    ("social", "Нийгэмшихүй", "#10b981"),
    ("emotional", "Сэтгэл хөдлөл", "#ec4899"),
    ("creative", "Бүтээлч сэтгэлгээ", "#8b5cf6"),
    ("self-care", "Өөртөө үйлчлэх чадвар", "#14b8a6"),
    ("communication", "Харилцаа", "#06b6d4"),
    ("habits", "Дадал хэвшил", "#84cc16"),
]

SCALE_NAME = "Үндсэн үнэлгээний шат"

LEVELS = [
    (1, "Дэмжлэг шаардлагатай", "#ef4444",
     "Тухайн чадварыг эзэмшихэд насанд хүрэгчийн тогтмол дэмжлэг хэрэгтэй."),
    (2, "Хөгжиж байгаа", "#f59e0b",
     "Чадвар төлөвшиж байгаа ч тогтвортой биш."),
    (3, "Хүлээгдэж буй түвшинд", "#10b981",
     "Насны онцлогт тохирсон түвшинд бие даан гүйцэтгэдэг."),
    (4, "Хүлээгдэж буй түвшнээс ахисан", "#3b82f6",
     "Насны хүлээлтээс давсан, бусдыг дэмжиж чаддаг."),
]

OBSERVATION_TYPES = [
    ("daily", "Өдөр тутмын ажиглалт"),
    ("artwork", "Бүтээл болон зурган ажиглалт"),
    ("activity", "Үйл ажиллагаанд суурилсан ажиглалт"),
    ("parent", "Эцэг эхийн оруулсан ажиглалт"),
]


def install_domains(DevelopmentDomain):
    """RFP §6.1."""
    for order, (code, name, color) in enumerate(DOMAINS, start=1):
        DevelopmentDomain.objects.get_or_create(
            kindergarten=None, code=code,
            defaults={"name": name, "color": color, "order": order},
        )


def install_scale(AssessmentScale, AssessmentLevel):
    """RFP §6.2."""
    scale, _ = AssessmentScale.objects.get_or_create(
        kindergarten=None, name=SCALE_NAME, defaults={"is_default": True},
    )
    for value, label, color, description in LEVELS:
        AssessmentLevel.objects.get_or_create(
            scale=scale, value=value,
            defaults={"label": label, "color": color,
                      "description": description},
        )
    return scale


def install_observation_types(ObservationType):
    """RFP §5.2."""
    for order, (code, name) in enumerate(OBSERVATION_TYPES, start=1):
        ObservationType.objects.get_or_create(
            kindergarten=None, code=code,
            defaults={"name": name, "order": order},
        )


def install():
    """Everything, using the real models. For tests and manual repair."""
    from apps.observations.models import ObservationType

    from .models import AssessmentLevel, AssessmentScale, DevelopmentDomain

    install_domains(DevelopmentDomain)
    install_scale(AssessmentScale, AssessmentLevel)
    install_observation_types(ObservationType)

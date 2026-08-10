"""The four observation types of RFP §5.2.

``Observation.type`` is required, so without these no observation can be
recorded at all. The rows live in ``apps/assessment/defaults.py`` alongside
the assessment configuration — same shape, same reason for being outside
the migration.
"""

from django.db import migrations

from apps.assessment.defaults import OBSERVATION_TYPES, install_observation_types


def create_defaults(apps, schema_editor):
    install_observation_types(apps.get_model("observations", "ObservationType"))


def remove_defaults(apps, schema_editor):
    ObservationType = apps.get_model("observations", "ObservationType")
    Observation = apps.get_model("observations", "Observation")

    if Observation.objects.exists():
        # Same reasoning as the assessment defaults: rolling this back would
        # orphan real records.
        return

    ObservationType.objects.filter(
        kindergarten=None, code__in=[code for code, _ in OBSERVATION_TYPES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [("observations", "0001_initial")]

    operations = [
        migrations.RunPython(create_defaults, remove_defaults),
    ]

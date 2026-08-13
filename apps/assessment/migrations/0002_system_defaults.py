"""The system-default domains and scale — RFP §6.1, §6.2.

The rows themselves live in ``apps/assessment/defaults.py``, because the
test suite needs to reinstall them: ``django_db(transaction=True)`` flushes
every table at teardown and takes migration-created data with it.

Reversible, and the reverse deletes only rows that are still untouched:
once an ``Assessment`` points at a level, removing it would take the
assessment with it.
"""

from django.db import migrations

from apps.assessment.defaults import DOMAINS, SCALE_NAME, install_domains, install_scale


def create_defaults(apps, schema_editor):
    install_domains(apps.get_model("assessment", "DevelopmentDomain"))
    install_scale(
        apps.get_model("assessment", "AssessmentScale"),
        apps.get_model("assessment", "AssessmentLevel"),
    )


def remove_defaults(apps, schema_editor):
    DevelopmentDomain = apps.get_model("assessment", "DevelopmentDomain")
    AssessmentScale = apps.get_model("assessment", "AssessmentScale")
    Assessment = apps.get_model("assessment", "Assessment")

    if Assessment.objects.exists():
        # Rolling back would orphan real assessments. Leaving the
        # configuration in place is harmless; deleting it is not.
        return

    AssessmentScale.objects.filter(kindergarten=None, name=SCALE_NAME).delete()
    DevelopmentDomain.objects.filter(
        kindergarten=None, code__in=[code for code, _, _ in DOMAINS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [("assessment", "0001_initial")]

    operations = [
        migrations.RunPython(create_defaults, remove_defaults),
    ]

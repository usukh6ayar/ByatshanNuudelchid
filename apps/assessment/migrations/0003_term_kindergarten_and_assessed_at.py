"""``Term`` becomes tenant-scoped, and ``assessed_at`` stops restamping.

Written by hand rather than by ``makemigrations``: adding a non-nullable
foreign key to a table that already has rows needs the three-step dance
below, and the automatic answer — a hard-coded default — would put every
existing term in one arbitrary kindergarten.

1. add the column as nullable
2. backfill it from each term's school year
3. tighten it to NOT NULL

Reversible in full: the reverse simply drops the column again.
"""

import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    Term = apps.get_model("assessment", "Term")
    for term in Term.objects.select_related("school_year").iterator():
        term.kindergarten_id = term.school_year.kindergarten_id
        term.save(update_fields=["kindergarten"])


def unfill(apps, schema_editor):
    """Nothing to undo — step 1's reverse drops the column."""


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0002_system_defaults"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="term",
            name="kindergarten",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.kindergarten",
            ),
        ),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(
            model_name="term",
            name="kindergarten",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.kindergarten",
            ),
        ),
        # auto_now → auto_now_add. RFP §6.4 wants the date the judgement was
        # made; auto_now restamped it on every unrelated write, including
        # opening the term to the guardians.
        migrations.AlterField(
            model_name="assessment",
            name="assessed_at",
            field=models.DateTimeField(auto_now_add=True,
                                       verbose_name="үнэлсэн огноо"),
        ),
    ]

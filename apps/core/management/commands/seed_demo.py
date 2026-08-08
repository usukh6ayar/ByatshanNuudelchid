"""Demo data for development — RFP §707.

Production data and real child photos are never copied into a development
environment, so there has to be something else to work against.

    docker compose run --rm web python manage.py seed_demo

Refuses to run when DEBUG is off, so it cannot be pointed at production by
accident.
"""

import datetime as dt
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Membership, Role, User
from apps.accounts.services import invite_teacher, register_guardian
from apps.children.models import Child, Guardianship
from apps.children.services import register_child
from apps.tenants.models import Group, Kindergarten, SchoolYear
from apps.tenants.services import assign_teacher

PASSWORD = "Demo-Nuuts99"

LAST_NAMES = ["Батбаяр", "Ганболд", "Дорж", "Отгонбаяр", "Сүхбаатар",
              "Тэмүүлэн", "Чинбат", "Энхбаяр"]
BOY_NAMES = ["Батаа", "Тэмүүлэн", "Энхжин", "Ганзориг", "Мөнх-Эрдэнэ", "Идэр"]
GIRL_NAMES = ["Сараа", "Энхриймаа", "Ануужин", "Номин", "Хулан", "Оюун"]


class Command(BaseCommand):
    help = "Create demo kindergartens, staff and children (development only)"

    def add_arguments(self, parser):
        parser.add_argument("--children", type=int, default=14)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo refuses to run with DEBUG off — RFP §707."
            )

        random.seed(20260808)

        boss = self._user("boss", "Системийн", "Админ", email="boss@example.mn")
        Membership.objects.get_or_create(user=boss, kindergarten=None,
                                         role=Role.SUPERADMIN)

        kindergarten = self._kindergarten()
        year = self._school_year(kindergarten)
        groups = [
            self._group(kindergarten, year, "Наранцэцэг", "3-4 нас"),
            self._group(kindergarten, year, "Бөмбөгөр", "4-5 нас"),
        ]

        director = self._user("director", "Болормаа", "Б.",
                              email="director@example.mn")
        Membership.objects.get_or_create(user=director,
                                         kindergarten=kindergarten,
                                         role=Role.ADMIN)

        for index, group in enumerate(groups, start=1):
            teacher, _, _ = invite_teacher(
                actor=director, kindergarten=kindergarten,
                last_name="Ариунзаяа", first_name=f"Багш {index}",
                username=f"teacher{index}",
                email=f"teacher{index}@example.mn",
            )
            teacher.set_password(PASSWORD)
            teacher.save(update_fields=["password"])
            assign_teacher(actor=director, group=group,
                           membership=teacher.memberships.get())

        self._children(director, groups, options["children"])

        for user in [boss, director]:
            user.set_password(PASSWORD)
            user.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS(
            f"\nDemo data ready. Password for every account: {PASSWORD}\n"
        ))
        self.stdout.write(
            "  superadmin  boss        → /udirdlaga/\n"
            "  admin       director    → /udirdlaga/\n"
            "  teacher     teacher1    → /bagsh/huuhded/\n"
            "  teacher     teacher2    → /bagsh/huuhded/\n"
            "  guardian    see below   → /etseg-eh/\n"
        )
        for link in Guardianship.objects.select_related("guardian_user")[:3]:
            self.stdout.write(f"              {link.guardian_user.phone}")

    # ------------------------------------------------------------------

    def _user(self, username, last_name, first_name, **extra):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"last_name": last_name, "first_name": first_name, **extra},
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user

    def _kindergarten(self):
        obj, _ = Kindergarten.objects.get_or_create(
            name="Бяцхан цэцэрлэг",
            defaults={
                "address": "Улаанбаатар, Сүхбаатар дүүрэг",
                "phone": "70001234",
                "email": "info@byatshan.mn",
                "description": "Хүүхдийн хөгжлийн цахим хувийн хавтас — жишиг өгөгдөл.",
            },
        )
        return obj

    def _school_year(self, kindergarten):
        obj, _ = SchoolYear.objects.get_or_create(
            kindergarten=kindergarten, name="2025-2026",
            defaults={
                "starts_on": dt.date(2025, 9, 1),
                "ends_on": dt.date(2026, 5, 31),
                "is_current": True,
            },
        )
        return obj

    def _group(self, kindergarten, year, name, age_category):
        obj, _ = Group.objects.get_or_create(
            kindergarten=kindergarten, school_year=year, name=name,
            defaults={"age_category": age_category},
        )
        return obj

    def _children(self, actor, groups, count):
        existing = Child.objects.count()
        for index in range(count):
            group = groups[index % len(groups)]
            is_girl = index % 2 == 0
            first_name = random.choice(GIRL_NAMES if is_girl else BOY_NAMES)

            child = register_child(
                actor=actor,
                group=group,
                last_name=random.choice(LAST_NAMES),
                first_name=first_name,
                national_id=f"CHD-{existing + index + 1:04d}",
                sex=Child.Sex.FEMALE if is_girl else Child.Sex.MALE,
                date_of_birth=dt.date(2021, 1, 1)
                + dt.timedelta(days=random.randint(0, 700)),
                health_notes="Самар, сүүний харшилтай." if index == 3 else "",
            )

            guardianship, _, _ = register_guardian(
                actor=actor, child=child,
                last_name=child.last_name, first_name="Ээж",
                relation=Guardianship.Relation.MOTHER,
                phone=f"9911{existing + index + 1:04d}",
                is_primary=True,
            )
            guardian = guardianship.guardian_user
            guardian.set_password(PASSWORD)
            guardian.save(update_fields=["password"])

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
from apps.assessment import selectors as assessment_selectors
from apps.assessment import services as assessment_services
from apps.children.models import Child, Guardianship
from apps.children.services import current_enrollment, register_child
from apps.comms import services as comms_services
from apps.comms.models import Announcement
from apps.observations import selectors as observation_selectors
from apps.observations import services as observation_services
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
            self._group(kindergarten, year, "Наранцэцэг", "3-4 нас",
                        Group.AgeBand.MIDDLE),
            self._group(kindergarten, year, "Бөмбөгөр", "4-5 нас",
                        Group.AgeBand.SENIOR),
        ]

        director = self._user("director", "Болормаа", "Б.",
                              email="director@example.mn")
        Membership.objects.get_or_create(user=director,
                                         kindergarten=kindergarten,
                                         role=Role.ADMIN)

        teachers = [
            self._teacher(director, kindergarten, group, index)
            for index, group in enumerate(groups, start=1)
        ]

        # RFP §6.4. Created here as well as by ``save_school_year`` so a
        # re-run against a database seeded before terms existed still ends
        # up with a working configuration.
        assessment_services.ensure_default_terms(actor=director,
                                                 school_year=year)
        self._extend_current_term(director, year)

        self._children(director, groups, options["children"])
        self._birthdays_today(groups)
        self._photos(director, groups)
        self._records(teachers, groups, year)
        self._portfolio(teachers, groups, year)
        self._parent_notes(teachers, groups)

        for user in [boss, director]:
            user.set_password(PASSWORD)
            user.save(update_fields=["password"])

        self._announcements(teachers, groups)

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
        """A school year that contains today, whenever the demo is seeded.

        The Mongolian academic year runs September to May, and hard-coding
        2025-2026 meant that from June onwards the demo had no current term.
        Without one, ``current_term`` returns None and the §12.1 assessment
        panel, the §6.3 grid and the §6.4 matrix all say "no term
        configured" while several hundred assessments sit in the table — the
        state this database was actually in.

        So the dates start from the real academic year and are stretched
        past today when the seed runs during the summer break.
        """
        today = dt.date.today()
        start_year = today.year if today.month >= 9 else today.year - 1
        starts_on = dt.date(start_year, 9, 1)
        ends_on = max(dt.date(start_year + 1, 5, 31),
                      today + dt.timedelta(days=30))

        obj, created = SchoolYear.objects.get_or_create(
            kindergarten=kindergarten, name=f"{start_year}-{start_year + 1}",
            defaults={"starts_on": starts_on, "ends_on": ends_on,
                      "is_current": True},
        )
        if not created and obj.ends_on < today:
            # Seeded before, and the year has since run out.
            obj.ends_on = ends_on
            obj.is_current = True
            obj.save(update_fields=["ends_on", "is_current"])
        return obj

    def _extend_current_term(self, actor, year):
        """Make sure some term contains today — RFP §6.4.

        ``ensure_default_terms`` divides whatever span the year had when it
        was first created, so a database seeded last season keeps four terms
        that all ended months ago. Stretching the last one is enough: every
        screen asks for "the term containing today", not for a tidy calendar.
        """
        today = dt.date.today()
        terms = list(year.terms.order_by("starts_on"))
        if not terms or any(t.starts_on <= today <= t.ends_on for t in terms):
            return

        last = terms[-1]
        last.ends_on = today + dt.timedelta(days=30)
        if last.starts_on > today:
            last.starts_on = today - dt.timedelta(days=30)
        last.save(update_fields=["starts_on", "ends_on"])

    def _teacher(self, director, kindergarten, group, index):
        """Invite a teacher, or reuse the one a previous run created.

        ``invite_teacher`` always creates, so without this a second
        ``seed_demo`` dies on the username unique constraint — and a command
        that only works once is a command nobody trusts.
        """
        username = f"teacher{index}"
        teacher = User.objects.filter(username=username).first()

        if teacher is None:
            teacher, _, _ = invite_teacher(
                actor=director, kindergarten=kindergarten,
                last_name="Ариунзаяа", first_name=f"Багш {index}",
                username=username, email=f"{username}@example.mn",
            )

        teacher.set_password(PASSWORD)
        teacher.save(update_fields=["password"])

        membership = teacher.memberships.filter(role=Role.TEACHER).first()
        if not group.teacher_assignments.filter(
            teacher_membership=membership
        ).exists():
            assign_teacher(actor=director, group=group, membership=membership)

        return teacher

    def _group(self, kindergarten, year, name, age_category, band=""):
        obj, _ = Group.objects.get_or_create(
            kindergarten=kindergarten, school_year=year, name=name,
            defaults={"age_category": age_category, "age_band": band},
        )
        return obj

    def _children(self, actor, groups, count):
        """Register up to ``count`` children, once.

        ``register_child`` always creates, so an unguarded second run added
        another fourteen — the demo grew by a class every time anyone re-ran
        it. The teachers were already protected this way; the children were
        not.
        """
        existing = Child.objects.count()
        if existing >= count:
            return

        count -= existing
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

    # ------------------------------------------------------- §12.1 tiles

    def _birthdays_today(self, groups):
        """Give two children today's birthday.

        The §12.1 tile and the birthday strip are otherwise permanently zero,
        and a dashboard panel nobody has ever seen populated is a panel
        nobody has checked. Only the month and day are moved — the year, and
        so the child's age, is left alone.
        """
        today = dt.date.today()
        children = [
            enrollment.child
            for group in groups
            for enrollment in group.enrollments.select_related("child")[:1]
        ]
        for child in children:
            if (child.date_of_birth.month, child.date_of_birth.day) == (
                today.month, today.day
            ):
                continue
            try:
                child.date_of_birth = child.date_of_birth.replace(
                    month=today.month, day=today.day
                )
            except ValueError:      # 29 February in a common year
                continue
            child.save(update_fields=["date_of_birth"])

    def _photos(self, actor, groups):
        """A profile picture for every child — RFP §3.4, §707.

        Drawn, not photographed. §707 forbids real children's images in a
        development environment, and the mockups show a face in every row, so
        the demo needs *something* in that slot: a coloured tile with the
        child's initial, which is also what the interface falls back to when
        a child has no photo.

        Going through ``set_child_photo`` rather than writing the row
        directly means the demo exercises the real path — MIME sniffed from
        content, pixels re-encoded, EXIF dropped, UUID storage key — so a
        break in upload shows up here rather than in production.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.media import services as media_services

        children = [
            enrollment.child
            for group in groups
            for enrollment in group.enrollments.select_related("child", "child__photo")
        ]

        for child in children:
            if child.photo_id:
                continue
            payload = self._placeholder_jpeg(child.first_name[:1] or "·",
                                             child.pk)
            if payload is None:
                return          # Pillow missing — skip photos, not the seed
            media_services.set_child_photo(
                actor=actor, child=child,
                upload=SimpleUploadedFile(f"{child.national_id}.jpg", payload,
                                          content_type="image/jpeg"),
            )

    def _placeholder_jpeg(self, letter: str, seed: int) -> bytes | None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None

        import io

        palette = [(91, 75, 214), (14, 165, 233), (22, 163, 74),
                   (234, 140, 26), (224, 81, 140), (13, 148, 136)]
        colour = palette[seed % len(palette)]

        image = Image.new("RGB", (320, 320), colour)
        draw = ImageDraw.Draw(image)
        # A lighter disc behind the letter, so the tile reads as a portrait
        # frame rather than a flat swatch at thumbnail size.
        draw.ellipse((60, 60, 260, 260),
                     fill=tuple(min(255, c + 46) for c in colour))
        draw.text((160, 150), letter, anchor="mm", fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    def _announcements(self, teachers, groups):
        """RFP §8.1 — one for everyone, one for a single group.

        Two is enough to show the targeting doing something: the parent
        screen looks identical with one notice whether or not the rule
        works.
        """
        if not teachers:
            return

        teacher, group = teachers[0], groups[0]
        if Announcement.objects.filter(kindergarten=group.kindergarten).exists():
            return

        whole = comms_services.save_announcement(
            actor=teacher, kindergarten_id=group.kindergarten_id,
            title="Эцэг эхийн хурал",
            body="Энэ пүрэв гарагт 18:00 цагт хурал болно. "
                 "Хүүхдийн хөгжлийн явцыг хамтдаа ярилцъя.",
            is_important=True,
        )
        comms_services.publish(actor=teacher, announcement=whole)

        targeted = comms_services.save_announcement(
            actor=teacher, kindergarten_id=group.kindergarten_id,
            title=f"{group.name} бүлгийн аялал",
            body="Баасан гарагт 09:00 цагт цугларна. Дулаан хувцастай ирээрэй.",
        )
        comms_services.set_targets(actor=teacher, announcement=targeted,
                                   groups=[group.pk])
        comms_services.publish(actor=teacher, announcement=targeted)

    def _portfolio(self, teachers, groups, year):
        """RFP §4.1–§4.3 — "Миний тухай" and the per-age pages.

        Left empty, the portfolio screen is nothing but four "Бөглөх" buttons
        and a completeness counter reading 0/4, which shows neither the
        layout nor the §10.1 PDF sections that read from these tables.

        Not every child gets every age. A portfolio that is uniformly full
        hides the thing the screen is actually for — seeing at a glance who
        still needs filling in.
        """
        from apps.portfolio import services as portfolio_services

        colours = ["Улаан", "Цэнхэр", "Ногоон", "Шар", "Ягаан", "Улбар шар"]
        foods = ["Бууз", "Цуйван", "Хуушуур", "Банштай шөл", "Ногоотой хоол"]
        toys = ["Тоглоомон машин", "Барилгын блок", "Зөөлөн баавгай",
                "Оньсого", "Хүүхэлдэй"]
        activities = ["Зураг зурах", "Дуулах", "Гадаа гүйх", "Ном үзэх",
                      "Бүжиглэх"]
        dreams = ["Эмч болно", "Багш болно", "Нисгэгч болно",
                  "Малын эмч болно", "Зураач болно"]
        traits = ["Тайван, ажигч.", "Хөгжилтэй, найрсаг.",
                  "Тэвчээртэй, анхаарал сайтай.", "Идэвхтэй, сониуч."]

        for teacher, group in zip(teachers, groups, strict=False):
            enrollments = list(
                group.enrollments.select_related("child").order_by("pk")
            )
            for index, enrollment in enumerate(enrollments):
                child = enrollment.child

                # Every fifth child is left blank on purpose.
                if index % 5 == 4:
                    continue

                portfolio_services.save_about_me(
                    actor=teacher, child=child,
                    introduction=f"{child.first_name} бол {traits[index % len(traits)].lower()} "
                                 f"Бүлгийн үйл ажиллагаанд дуртай оролцдог.",
                    name_meaning="Нэрийн утга: аз жаргал, эрүүл энх.",
                    memorable_sayings="«Би өөрөө хийж чадна!»",
                    dream=dreams[index % len(dreams)],
                    distinguishing_traits=traits[index % len(traits)],
                    height_cm=95 + index % 18,
                    weight_kg=14 + index % 7,
                    recorded_on=dt.date.today() - dt.timedelta(days=14),
                )

                # Ages up to the child's current one, so the timeline reads
                # as a history rather than as a form filled in ahead of time.
                for age in range(2, min(child.age, 5) + 1):
                    portfolio_services.save_age_profile(
                        actor=teacher, child=child, age=age,
                        school_year=year,
                        favorite_color=colours[(index + age) % len(colours)],
                        favorite_food=foods[(index + age) % len(foods)],
                        favorite_toy=toys[(index + age) % len(toys)],
                        favorite_activity=activities[(index + age) % len(activities)],
                        favorite_song="Намрын шар навч",
                        personality=traits[(index + age) % len(traits)],
                        family_members="Ээж, аав, эгч.",
                    )
                    portfolio_services.save_birthday_note(
                        actor=teacher, child=child, age=age,
                        note=f"{age} насны төрсөн өдрийг бүлгээрээ тэмдэглэв. "
                             f"Бялуу хийж, дуу дуулсан.",
                    )

    def _parent_notes(self, teachers, groups):
        """RFP §5.4 — what a guardian submitted, waiting for a teacher.

        This is the one flow with a queue behind it. With nothing pending,
        the review screen, the §12.1 "Хянах ажиглалт" tile and the badge on
        the dashboard are all empty, and none of them has been seen working.
        One note per group is left approved so the parent-visible side has
        something in it too.
        """
        notes = [
            ("Гэртээ ном уншсан", "Оройн хоолны дараа",
             "Өөрөө хуудас эргүүлж, зургийг нэрлэн тайлбарлав."),
            ("Дүүгээ асарсан", "Амралтын өдөр",
             "Дүүгээ тоглоомоор хамт тоглуулж, эвтэй байв."),
            ("Хоол хийхэд туслав", "Бямба гарагийн өглөө",
             "Гурил зуурахад тусалж, гараа өөрөө угаасан."),
        ]

        for teacher, group in zip(teachers, groups, strict=False):
            types = list(observation_selectors.types_for(group.kindergarten_id))
            if not types:
                continue

            enrollments = list(
                group.enrollments.select_related("child").order_by("pk")[:3]
            )
            for index, enrollment in enumerate(enrollments):
                child = enrollment.child
                link = child.guardianships.select_related("guardian_user").first()
                if link is None:
                    continue
                if child.observations.filter(source="parent").exists():
                    continue

                activity, situation, did = notes[index % len(notes)]
                note = observation_services.create_observation(
                    actor=link.guardian_user, child=child,
                    source="parent", type=types[0],
                    observed_on=dt.date.today() - dt.timedelta(days=index + 1),
                    activity_name=activity, situation=situation, child_did=did,
                )

                # The first of each group is approved; the rest stay pending
                # so the queue has something in it.
                if index == 0:
                    observation_services.review_observation(
                        actor=teacher, observation=note, status="approved",
                        note="Баярлалаа, хавтаст нь оруулав.",
                        include_in_report=True,
                    )

    def _records(self, teachers, groups, year):
        """A few observations and assessments — RFP §5.1, §6.3.

        Enough for the screens to have something in them; not so much that
        the demo takes a minute to seed.
        """
        term = assessment_selectors.current_term(year) or year.terms.first()
        if term is None:
            return

        situations = [
            ("Өглөөний дасгал", "Бүлгээрээ дасгал хийж байх үед",
             "Хөгжимд тааруулан гараа өргөж, үсрэх хөдөлгөөнийг дуустал хийсэн.",
             "«Би чадаж байна!»"),
            ("Зураг зурах", "Чөлөөт үйл ажиллагааны цагаар",
             "Гэр бүлээ зурж, гишүүн бүрийг нэрлэн тайлбарлав.",
             "«Энэ бол миний ээж, энэ бол дүү минь.»"),
            ("Блокоор барих", "Хосоороо тоглож байхад",
             "Найзтайгаа ээлжлэн блок өрж, цамхаг барив.",
             "«Чи эхлээд тавь, дараа нь би.»"),
        ]

        for teacher, group in zip(teachers, groups, strict=False):
            types = list(observation_selectors.types_for(group.kindergarten_id))
            domains = list(
                assessment_selectors.domains_for(group.kindergarten_id)
            )
            levels = list(assessment_selectors.levels_for(group.kindergarten_id))
            if not (types and domains and levels):
                continue

            # Every child, not the first four. §6.3's grid is a whole group
            # against nine domains, and a matrix with four populated rows
            # does not show whether the screen works.
            children = [
                enrollment.child
                for enrollment in group.enrollments.select_related("child")
            ]

            # The term before the current one, where there is one, so §6.4's
            # matrix has two columns to compare and the portfolio PDF shows
            # progress rather than a single reading.
            previous = (
                year.terms.filter(starts_on__lt=term.starts_on)
                .order_by("-starts_on").first()
            )

            for index, child in enumerate(children):
                enrollment = current_enrollment(child)
                if enrollment is None:
                    continue

                # `create_observation` always creates, so without this a
                # second run doubles every child's history. The assessments
                # below go through `save_assessment`, which updates in place
                # and needs no such guard.
                already = child.observations.filter(source="teacher").exists()

                # Two or three observations each, spread over the last few
                # weeks so the lists sort into a plausible order.
                for repeat in range(0 if already else 2 + index % 2):
                    activity, situation, did, said = situations[
                        (index + repeat) % len(situations)
                    ]
                    observation_services.create_observation(
                        actor=teacher, child=child,
                        type=types[(index + repeat) % len(types)],
                        observed_on=dt.date.today()
                        - dt.timedelta(days=index + repeat * 9),
                        activity_name=activity, situation=situation,
                        child_did=did, child_said=said,
                        teacher_comment="Идэвхтэй оролцов.",
                        next_steps="Дараагийн долоо хоногт бүлгийн өмнө ярих дасгал.",
                        domains=[(domains[(index + repeat) % len(domains)],
                                  levels[(index + repeat) % len(levels)])],
                    )

                # Every fourth child is left part-assessed on purpose, so the
                # §12.1 "Үнэлгээ дутуу" tile and the list under it are not
                # permanently zero.
                covered = domains if index % 4 else domains[:4]

                for domain in covered:
                    assessment_services.save_assessment(
                        actor=teacher, child=child, enrollment=enrollment,
                        domain=domain, term=term,
                        level=levels[(index + domain.order) % len(levels)],
                    )
                    if previous is not None:
                        # A level lower last term, so the matrix reads as
                        # movement. max() keeps it inside the scale.
                        earlier = levels[
                            max(0, (index + domain.order) % len(levels) - 1)
                        ]
                        assessment_services.save_assessment(
                            actor=teacher, child=child, enrollment=enrollment,
                            domain=domain, term=previous, level=earlier,
                        )

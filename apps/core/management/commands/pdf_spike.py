"""Week-one risk spike — spec section 13.1.

Generates a sample PDF containing Mongolian text, a photo, a logo and page
numbers. Print it at A4 and look at it. Automated checks catch a missing
font; only a human catches bad kerning, clipped diacritics or a stretched
photo.

    docker compose run --rm web python manage.py pdf_spike
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.core.pdf import data_uri, font_covers_mongolian, render_pdf


class Command(BaseCommand):
    help = "Render a Mongolian Cyrillic sample PDF (RFP §10.3 risk spike)"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="/app/spike.pdf")
        parser.add_argument("--font", default="DejaVu Sans")
        parser.add_argument("--photo", default="")
        parser.add_argument("--logo", default="")

    def handle(self, *args, **options):
        ok, message = font_covers_mongolian(options["font"])
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Font check: {message}"))
        else:
            self.stdout.write(self.style.ERROR(f"Font check FAILED: {message}"))
            self.stdout.write(
                "Add a Cyrillic-capable font to assets/fonts/ and rebuild the image."
            )

        pdf = render_pdf(
            "reports/spike.html",
            {
                "photo_data_uri": data_uri(options["photo"]) if options["photo"] else None,
                "logo_data_uri": data_uri(options["logo"]) if options["logo"] else None,
            },
        )

        out = Path(options["out"])
        out.write_bytes(pdf)

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {out} ({len(pdf):,} bytes)")
        )
        self.stdout.write(
            "\nNow verify by hand — spec section 13.1:\n"
            "  1. Ө ө Ү ү render as letters, not boxes\n"
            "  2. Print at A4: nothing clipped at the margins\n"
            "  3. Page number appears in the footer\n"
            "  4. The photo keeps its aspect ratio\n"
        )

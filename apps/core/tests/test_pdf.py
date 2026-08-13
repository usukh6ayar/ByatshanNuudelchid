"""PDF rendering tests — RFP §10.3, the highest-risk requirement.

These catch a missing font, missing glyphs, an unembedded font and broken
text encoding. They cannot judge whether the output *looks* right; that needs
the ``pdf_spike`` command and a printed A4 page (spec section 13.1).
"""

import io
import subprocess

import pytest

from apps.core.pdf import font_covers_mongolian, render_pdf

FONT_FAMILY = "DejaVu Sans"

# Mongolian Cyrillic letters absent from Russian Cyrillic. A font can pass a
# naive "has Cyrillic" check and still be missing exactly these.
MONGOLIAN_ONLY_CODEPOINTS = {
    0x04E8: "Ө", 0x04E9: "ө", 0x04AE: "Ү", 0x04AF: "ү",
}

A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89


@pytest.fixture(scope="module")
def spike_pdf() -> bytes:
    return render_pdf(
        "reports/spike.html", {"photo_data_uri": None, "logo_data_uri": None}
    )


@pytest.fixture(scope="module")
def reader(spike_pdf):
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(spike_pdf))


def _font_path(family: str = FONT_FAMILY) -> str:
    return subprocess.run(
        ["fc-match", "-f", "%{file}", family],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout.strip()


# ------------------------------------------------------------------ the font

def test_cyrillic_font_is_installed():
    """The most common cause of □□□ in generated PDFs."""
    ok, message = font_covers_mongolian(FONT_FAMILY)
    assert ok, message


@pytest.mark.parametrize(
    ("codepoint", "char"), sorted(MONGOLIAN_ONLY_CODEPOINTS.items())
)
def test_font_has_a_glyph_for_mongolian_letter(codepoint, char):
    """Read the font's character map directly."""
    from fontTools.ttLib import TTFont

    font = TTFont(_font_path(), fontNumber=0)
    covered = any(codepoint in table.cmap for table in font["cmap"].tables)

    assert covered, (
        f"{FONT_FAMILY} has no glyph for U+{codepoint:04X} ({char}). "
        f"It renders as a box in every PDF."
    )


# ------------------------------------------------------------------ the PDF

def test_renders_a_valid_pdf(spike_pdf):
    assert spike_pdf.startswith(b"%PDF-"), "output is not a PDF"
    assert len(spike_pdf) > 5_000, f"suspiciously small PDF ({len(spike_pdf)} bytes)"


def test_page_is_a4(reader):
    """RFP §10.3 — suitable for printing at A4."""
    box = reader.pages[0].mediabox
    assert float(box.width) == pytest.approx(A4_WIDTH_PT, abs=1)
    assert float(box.height) == pytest.approx(A4_HEIGHT_PT, abs=1)


def test_font_is_embedded(reader):
    """An unembedded font renders differently on every other machine.

    WeasyPrint writes compressed object streams, so this must be parsed
    rather than grepped for.
    """
    fonts = reader.pages[0]["/Resources"]["/Font"]
    assert fonts, "the page references no fonts at all"

    embedded = []
    for font in fonts.values():
        font = font.get_object()
        descriptor = font.get("/FontDescriptor") or (
            font.get("/DescendantFonts", [{}])[0].get_object().get("/FontDescriptor")
            if font.get("/DescendantFonts") else None
        )
        if descriptor and any(
            key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")
        ):
            embedded.append(str(font.get("/BaseFont")))

    assert embedded, f"no embedded font among {[str(f) for f in fonts]}"


@pytest.mark.parametrize("char", sorted(MONGOLIAN_ONLY_CODEPOINTS.values()))
def test_mongolian_letters_survive_the_round_trip(reader, char):
    """Extracted text proves the ToUnicode mapping is correct.

    If this fails, the letters may still look right on screen but copy,
    search and screen readers all produce garbage.
    """
    text = reader.pages[0].extract_text()
    assert char in text, f"{char!r} did not survive PDF encoding"


def test_page_number_is_rendered(reader):
    """RFP §10.3 — page numbers required."""
    assert "Хуудас 1 / 1" in reader.pages[0].extract_text()

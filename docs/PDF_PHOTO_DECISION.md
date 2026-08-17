# Decision gate — observation photos in the portfolio PDF

**Date:** 2026-08-17 · **Status:** decided, not implemented · **Scope:** Phase 1 closure

## The question

The generated portfolio PDF renders the **Багшийн ажиглалт** and **Эцэг эхийн
ажиглалт** sections as text. Photographs attached to those observations are
not embedded. Should Phase 1 embed them?

## Classification

> ### B. CAN DEFER TO PHASE 2 / POST-MVP

This does **not** need product approval to defer. The deferral is already
written down and already agreed — see the evidence below. It would need
approval to *build*, because building it pulls a Phase 2 item forward.

## Evidence

### 1. The PDF requirement asks for one photo, and it is there

RFP §10.3 lists what a PDF must satisfy. The image line is:

> Хүүхдийн зурагтай

Singular — *with the child's photo*. `templates/reports/child_portfolio.html`
embeds exactly that on the cover as a data URI, alongside the kindergarten
logo, both with `object-fit` so §10.3's *"Зураг суналт, гажилтгүй"* holds.
The requirement is met as written.

### 2. Observation photos are the "photo album", which is Phase 2

RFP §10.1 lists the sections a full report may include. Photographs appear
there as their own selectable section — **Зургийн цомог** — separate from
**Багшийн ажиглалт**. That section is not implemented, and its deferral is
explicit in `ROADMAP.md` (D1, amended 2026-08-12):

> The rest of D1's list stays in Phase 2 — the full portfolio timeline,
> milestones, **photo albums**, growth tracking, document library,
> `AnnualReport` (§6.5), Excel, activity posts and consent records.

`CLAUDE.md` §7.1 repeats "photo albums" in its Phase 2 list. Embedding
observation photographs is the PDF half of that feature.

### 3. The acceptance criterion is about rendering, not inventory

RFP §21.8:

> PDF дээр Монгол үсэг болон зураг зөв харагддаг байх.

The claim is that Mongolian type and images *render correctly* — not that
every image in the system appears. Both are verified: Cyrillic through
DejaVu Sans installed in the image, and images through the cover photo and
logo. This was checked by rasterising real 8- and 13-page PDFs with
`pdftoppm` and inspecting the pages, not by reading the template.

### 4. Deferring costs nothing that Phase 1 promises

§20-II's mandatory MVP list pulled **Улирлын тайлан** into Phase 1 (ROADMAP
D1) precisely because §21.7 made it an acceptance criterion. No equivalent
line makes observation photographs in the PDF an acceptance criterion. The
photographs are not lost — they are visible in the web portfolio, which is
where Phase 1 puts them.

## Residual risk, flagged not resolved

§21.8's wording — *"Mongolian text and images display correctly"* — is
terse enough that a client reading it at acceptance could expect photographs
*throughout* the report rather than on the cover. The technical reading above
is sound and matches §10.3's explicit singular, but this is a wording the
client may read differently than we do.

**Recommended handling:** raise it at acceptance review as a one-line
confirmation ("the PDF carries the child's cover photo; the photo album is
Phase 2 as agreed in D1"), rather than pre-emptively building a Phase 2
feature against a maybe.

## If it is later pulled forward

Not a template change alone. The work is:

- fetch each attachment's bytes through the permission layer, never by URL
  (CLAUDE.md §1.4) — the PDF renderer must not reach storage directly;
- inline as data URIs, as the cover photo already does, since WeasyPrint
  must not make network calls during a render;
- bound the count and the pixel dimensions, or §10.3's *"Том файл
  үүсгэхгүйгээр чанарыг хадгалах"* fails on a child with a year of photos;
- the resizing belongs in Celery (CLAUDE.md §6), which is where Phase 2 puts
  image conversion anyway.

That last point is the real reason this is Phase 2 rather than an afternoon:
it wants the image pipeline that Phase 2 builds.

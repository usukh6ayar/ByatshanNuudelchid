# Mockup fidelity audit

**Date:** 2026-08-17 · **Branch:** `feat/ui-redesign` · **Baseline:** 932 tests passing

Measures the redesigned UI against the client's 21 approved mockups in
`docs/design/screens/`. RFP §21.15 makes those images the visual acceptance
target ("the system must match the design and user flows the client
approved"), so this asks one question only:

> **Does the implementation visually match the approved mockup?**

Not "is it good". A screen that is calmer, more accessible and better on a
phone than the mockup is still a mismatch if the client approved something
else. Several findings below are exactly that.

## Method

Nine mockup images were opened and examined directly — not read from
`INDEX.md`, not inferred from filenames:

`parent-home` · `teacher-dashboard` · `teacher-children-list` ·
`teacher-child-profile-360` · `teacher-observation-form` ·
`teacher-assessment-matrix` · `teacher-report-builder-pdf` ·
`teacher-feed-and-messages` · `overview-mobile-app-screens`

Each was compared against the current template and its rendered output at
375 / 768 / 1440, captured during the redesign.

**Not examined** (no implemented counterpart): the three admin dashboards,
the SaaS operator view, `teacher-attendance-health`,
`teacher-surveys-analytics`, the four overview sheets beyond the mobile one,
and the two `-alt` variants. `auth-login-and-password-reset` was not examined
because the auth screens were never in the redesign scope.

---

## 1. Overall visual fidelity score

Two figures, because one number would mislead.

| Measure | Score | What it means |
|---|---|---|
| **Raw fidelity** | **≈50%** | Every visual difference counted, including content the ROADMAP deliberately defers |
| **Fidelity within Phase 1 scope** | **≈65%** | Counting only differences that are *not* explained by a deferred feature |

The 15-point gap is Phase 2 and 3 content the mockups draw and the build
deliberately omits — attendance, meals, payments, surveys, the post feed,
growth charts, milestones, voice notes, tags. `docs/design/INDEX.md` already
records that decision and it is not re-litigated here.

**The honest summary:** the *design language* is close — colour, radius,
badge treatment and the white sidebar are faithful. The *structure* is not.
Three screens are substantially different from what the client approved, and
one shared piece of chrome is missing from every teacher screen.

---

## 2. Screen-by-screen status

| Screen | Mockup | Current | Status | Priority | Main mismatch |
|---|---|---|---|---|---|
| Shared teacher shell | all teacher sheets | `base_teacher.html` | **PARTIAL** | **P1** | No top bar: no breadcrumb, school-year selector, search, or notification bell |
| Shared parent shell | `parent-home` | `base_parent.html` | **MATCH** | — | Faithful; bottom nav is an addition the mobile sheet supports |
| Teacher dashboard | `teacher-dashboard` | `dashboard/teacher.html` | **PARTIAL** | **P1** | 4 stat tiles vs 6; bar meters vs donut; quick actions are text rows vs a 6-tile colour grid |
| Parent home | `parent-home` | `children/parent/home.html` | **PARTIAL** | **P1** | Domain progress bars missing (data exists); quick-link grid 4 vs 9; child card lacks the two drawn buttons |
| Parent child detail | `teacher-child-profile-360` | `children/parent/detail.html` | **PARTIAL** | P2 | No tab strip; no "Товч тойм" stat row |
| Teacher children list | `teacher-children-list` | `children/teacher/list.html` | **MISMATCH** | **P0** | Mockup is a dense 11-column table with photos, №, Excel import/export and icon actions. Implementation is card rows |
| Teacher child detail | `teacher-child-profile-360` | `children/teacher/detail.html` | **PARTIAL** | **P1** | No 11-tab strip; no milestone timeline; no photo album; no "Товч тойм" cards |
| Observation form | `teacher-observation-form` | `observations/form.html` | **PARTIAL** | **P1** | No right rail (child card, stats, completeness checklist, 3 actions); no character counters; level UI differs |
| Observation list | — | `observations/list.html` | **NO MOCKUP** | — | Nothing to measure against |
| Assessment group grid | `teacher-assessment-matrix` | `assessment/group_grid.html` | **MISMATCH** | **P0** | Mockup is children × 9 domains with dot cells and a detail rail. Implementation is one domain at a time |
| Portfolio overview | — (a tab in `-360`) | `portfolio/overview.html` | **NO DIRECT MOCKUP** | P3 | Only measurable as a tab of the 360° screen |
| Comms list | `teacher-feed-and-messages` | `comms/list.html` | **PARTIAL** | P2 | Mockup is a post feed with 6 tabs and a right rail; implementation is the Мэдэгдэл tab only (Phase-gated) |
| Comms detail | `teacher-feed-and-messages` | `comms/detail.html` | **PARTIAL** | P2 | No pinned-notice treatment; no right rail |
| Reports request | `teacher-report-builder-pdf` | `reports/request.html` | **MISMATCH** | **P1** | No report-type tiles, no term buttons, no settings block, **no live PDF preview** |
| Reports status | — | `reports/status.html` | **NO MOCKUP** | — | Nothing to measure against |
| Child portfolio PDF | preview pane of `-report-builder` | `reports/child_portfolio.html` | **MISMATCH** | **P1** | No photo grid, no donut charts, no illustrated band, no tinted child card |

**Counts:** 1 MATCH · 8 PARTIAL · 4 MISMATCH · 3 NO MOCKUP · 0 NOT IMPLEMENTED.

---

## 3. P0 and P1 mismatches

### P0-1 · Assessment grid is not the approved matrix

`teacher-assessment-matrix.jpeg` shows **18 children down, 9 development
domains across**, each cell a coloured dot, a right-hand panel holding the
selected child's full assessment, a batch save bar, and counts of assessed
versus unassessed.

The implementation assesses **one domain at a time** and shows a list of
children with level chips.

This is not a styling gap. It is a different screen answering a different
question — the mockup lets a teacher read a whole group across every domain
at once, which is the stated point of §6.3's "нэг дэлгэц".

It is also **not purely a UI fix**: `selectors.group_grid(user, group, term,
domain)` takes a single domain, and the view resolves it from `?domain=`.
The matrix needs a new selector and a wider save contract. This was reported
during the assessment checkpoint and the single-domain approach was approved
then — but it was approved as an implementation constraint, not as a
deviation from the client's approved design, and §21.15 measures the latter.

### P0-2 · Children list is a card list where the client approved a table

`teacher-children-list.jpeg` is a genuine data table: №, photo, code, name,
sex, date of birth, age, enrolment date, status, guardians, actions — eleven
columns, ten rows visible, with Excel import/export above it and icon-only
row actions.

The implementation shows card rows with name, code, age, group and status,
having deliberately dropped sex and date of birth as not helping anyone find
a child.

Two sub-findings worth separating:

* **Excel import/export** is drawn in the mockup and is explicitly Phase 2 in
  `INDEX.md`. Not a fidelity failure.
* **Everything else** — the table itself, the column set, the density, the
  per-page selector, numbered pagination — is a real structural mismatch.

### P1-1 · No top bar on any teacher screen

Every teacher mockup — dashboard, children list, observation form, matrix,
report builder, feed — carries the same top bar:

`[hamburger] Page title / breadcrumb ······ [school-year select] [search] [bell + count] [mail + count] [avatar + name + role]`

The implementation has a page title and an identity pill. Missing:
breadcrumb, school-year selector, global search, notification bell with
count, message icon.

This affects **all eight teacher screens** and is the single most repeated
difference in the whole audit. The bell and its unread count are §8.1
functionality that already exists in the data layer; the school-year
selector is drawn on six of nine sheets.

### P1-2 · No right rail on the working screens

Four mockups put a persistent right column beside the main content:

| Screen | Right rail holds |
|---|---|
| Observation form | Child card · observation stats · tags · **completeness checklist** · tip · 3 actions |
| Assessment matrix | Selected child's detail: level, date, teacher, comment, strengths, needs, next goals |
| Report builder | **Live PDF preview** with page thumbnails |
| Feed | Daily summary · recent messages · quick-send tiles |

Only `children/teacher/detail.html` has a two-column layout. The other three
are single-column.

The observation form's **"Маягтын бүрдэлт"** checklist is the most valuable
single item here: six ticks showing which parts of the form are done. It is
buildable today from fields the form already has.

### P1-3 · Report request has no preview and no type tiles

The mockup is a two-column builder: report type as four icon tiles, child
selector, term as four buttons, sections as a two-column checklist, a
settings block (language, page size, design template, watermark), and a
**live PDF preview with page thumbnails, zoom and print**.

The implementation is a one-column form with two selects and a checkbox
list. No preview, no tiles, no settings.

Preview is the biggest miss — the mockup makes the PDF visible *before*
committing, and the current flow is generate-then-look.

### P1-4 · PDF is far plainer than the approved preview

The report-builder mockup shows the intended PDF clearly enough to compare:

| Mockup PDF | Current PDF |
|---|---|
| Logo + kindergarten name header band | Logo on cover only |
| Cream/peach child card, photo right, facts with icons | Lavender cover panel, photo above name |
| **Illustrated scene band** (houses, trees, children) | None |
| **Photo grid** — 4 term highlights | None (cover photo only) |
| **Donut charts** per domain with % | Assessment table |
| Narrative teacher summary | Present (term report) |

The photo grid is the most consequential: `builder.build_context` inlines
only the cover photograph, so the keepsake contains no pictures of the child
at work. Reported during the reports checkpoint; still open.

### P1-5 · Teacher dashboard tile row and chart

Mockup: **six** KPI tiles (children, present today, birthdays, new notices,
missing assessments, term progress) and a **donut** for domain averages.
Implementation: four tiles, horizontal bar meters.

Two of the six tiles (attendance) are Phase 3 and correctly absent. The tile
*count* and the donut are the fidelity gap.

---

## 4. Shared design-system mismatches

| Element | Mockup | Current | Verdict |
|---|---|---|---|
| Sidebar colour | White on 6 of 7 sheets; **dark indigo on `teacher-children-list` only** | White | **MATCH** — the majority reading is right, and `app.css` already documents it |
| Sidebar nav | Nested/collapsible (Үнэлгээ → 4 children) | Flat | PARTIAL, P2 |
| Sidebar footer | Storage bar (12.6 GB / 50 GB), current group, school year, help box, app-store banner | Theme toggle only | PARTIAL, P3 — storage quota has no field in the model (`INDEX.md`, "Still open") |
| Top bar | Present on every teacher sheet | Absent | **MISMATCH, P1** |
| Primary colour | Blue-violet ≈`#6366F1` | `#6c63ff` | **MATCH** |
| Assessment level colours | red / amber / green / blue | `AssessmentLevel.color` = `#ef4444` `#f59e0b` `#10b981` `#3b82f6` | **MATCH** |
| Corner radius | ~12–16px panels, pill badges | 12–18px panels, pill badges | **MATCH** |
| Shadows | Very soft, near-hairline | Same | **MATCH** |
| Badges/pills | Tinted, rounded, small caps | Same | **MATCH** |
| Icons | Outline, ~20px, one weight | Outline sprite, 20px | **MATCH** |
| Buttons | Solid violet primary, white ghost | Same | **MATCH** |
| Empty states | Not drawn in any mockup | Icon + message + action | **NO MOCKUP** |

**The design system itself is largely faithful.** The mismatches are
structural — chrome and layout — not tokens.

---

## 5. Typography mismatch

The mockups are set in a geometric grotesque — the letterforms match
Inter/Manrope: single-storey `a` in headings, tall x-height, tight tracking
on large numerals.

The implementation uses `system-ui` (SF Pro on macOS, Segoe UI on Windows,
Roboto on Android). Close in feel; not the same face, and it **changes
between the client's machine and a teacher's**.

Weight and hierarchy are close. Sizes are close. The specific typeface is
not, and cannot be without either a CDN (excluded by the stack decision) or
self-hosting ~200 KB of Cyrillic glyphs.

**Status: PARTIAL, P2.** Worth an explicit client decision rather than a
silent substitution.

---

## 6. Colour mismatch

Essentially none. Primary violet, the four assessment-level colours, the
pastel statistic tints and the warm neutral ground all read as the mockups
do.

Two small ones:

* Mockup page ground is a cooler near-white; ours is warmer (`#faf9f6`). A
  deliberate §13 choice ("дулаан өнгө төрх"), defensible, but a difference.
* Mockup domain chips use stronger tints than ours at the same size.

**Status: MATCH.** P3 at most.

---

## 7. Navigation mismatch

| | Mockup | Current |
|---|---|---|
| Teacher sidebar entries | 12–14, several nested | 6, flat |
| Deferred entries drawn | Ирц, Эрүүл мэнд, Хоол, Санхүү, Судалгаа, Медиа | Correctly omitted |
| Breadcrumb | On every inner screen | None |
| Global search | In the top bar | None |
| Year/term selector | In the top bar | Per-screen filters only |
| Parent nav | 11 entries | 3 + bottom bar |

Omitting deferred entries is the right call and `INDEX.md` says so
explicitly. **Breadcrumb and global search are not deferred features** —
they are chrome the mockups show on every screen. P1/P2.

---

## 8. Density and layout mismatch

The mockups are consistently **denser** than the implementation.

| Screen | Mockup shows | Current shows |
|---|---|---|
| Children list | 10 children + 11 columns above the fold | ~8 children, 5 fields |
| Assessment | 9 children × 9 domains = 81 cells | 16 children × 1 domain |
| Dashboard | 6 tiles + 8 panels | 4 tiles + 6 sections |
| Observation form | 6 sections + right rail on one screen | 5 sections, scrolling |

This is the deepest disagreement between the approved design and the built
product, and it is a *decision*, not an oversight: the redesign brief for
every checkpoint asked for calm, whitespace and "not an enterprise table",
while the mockups are information-dense SaaS screens.

**Both cannot be satisfied.** §21.15 points at the mockups.

---

## 9. Mobile mismatches

Only one mockup sheet covers mobile: `overview-mobile-app-screens.jpeg`, and
it draws a **native app**, not a responsive web layout — the ROADMAP puts
native apps out of scope entirely.

Measured against it as a *visual* reference:

| Element | Mobile sheet | Current | Verdict |
|---|---|---|---|
| Bottom navigation | 4–5 items, raised centre action | 3 items, no raised action | PARTIAL, P2 |
| Header | Violet card with greeting | White bar with brand | PARTIAL, P2 |
| Home tile grid | 3×3 coloured tiles | 2×2 on the child page | PARTIAL, P2 |
| List items | Compact, avatar + two lines | Same | MATCH |
| Section rhythm | Generous | Same | MATCH |

The parent mobile experience is **closer to the mockup than the desktop
screens are**, because the bottom bar and tile grid were taken from this
sheet directly.

No mockup covers teacher mobile at all.

---

## 10. Parent-side mismatches

1. **Domain progress bars missing from the home screen** — drawn in
   `parent-home` as five labelled bars with percentages. The data exists
   (`dashboard.selectors` computes domain averages). **P1, and buildable
   today.**
2. **Quick links 4 vs 9** — five of the nine are deferred; the four built are
   correct. P3.
3. **Child card lacks the two drawn buttons** — "Хүүхдийн 360° хуудас" and
   "Портфолио үзэх" sit prominently on the mockup card. P2.
4. **No "Өнөөдрийн мэдээлэл" strip** — six tinted chips (mood, meals, sleep,
   temperature). Phase 3. Correctly absent.
5. **No teacher post feed** — Phase 2. Correctly absent.

## 11. Teacher-side mismatches

Covered above. In priority order: assessment matrix (P0), children list
table (P0), top bar (P1), right rails (P1), report preview (P1), dashboard
tiles (P1), tab strip on the child page (P1), nested sidebar (P2).

---

## Top 10 mismatches, ranked

| # | Mismatch | Screen(s) | Priority | Backend work? |
|---|---|---|---|---|
| 1 | Single-domain assessment instead of the approved matrix | Assessment grid | **P0** | **Yes** — new selector + save contract |
| 2 | Card list instead of the approved data table | Children list | **P0** | No |
| 3 | No top bar (breadcrumb, year, search, bell) | All 8 teacher screens | **P1** | Partly — search needs a view |
| 4 | No right rail | Observation form, matrix, report builder | **P1** | No |
| 5 | No live PDF preview or report-type tiles | Reports request | **P1** | Maybe — preview needs a render endpoint |
| 6 | PDF has no photo grid, donuts or illustration | Child portfolio PDF | **P1** | **Yes** — builder must inline observation media |
| 7 | Dashboard: 4 tiles and bars vs 6 tiles and a donut | Teacher dashboard | **P1** | No |
| 8 | No tab strip on the child page | Teacher + parent child detail | **P1** | No |
| 9 | Parent home missing domain progress bars | Parent home | **P1** | No — data already computed |
| 10 | Typeface is `system-ui`, not the mockup's geometric sans | Everywhere | **P2** | No — needs a font decision |

---

## Recommendations

### Which screens to redesign first

1. **Assessment group grid** — the only P0 that is also an acceptance
   criterion (§6.3 *and* §21.15). Needs a backend decision before any UI work.
2. **Children list** — highest-traffic teacher screen, pure presentation
   work, no backend involved.
3. **Shared teacher shell (top bar)** — one file, improves eight screens.
4. **Observation form right rail** — the completeness checklist is the
   highest-value single element in the mockups.
5. **Reports request + PDF** — the client's own preview sets the bar for
   what a parent receives.

### Estimated templates affected

| Work | Templates | Notes |
|---|---|---|
| Top bar | 1 (`base_teacher.html`) + `app.css` | Affects 8 screens |
| Children list table | 1 | |
| Assessment matrix | 1 + selector + view + service | Backend change |
| Observation form rail | 1 | |
| Reports request + preview | 1–2 | Preview may need a view |
| PDF photo grid + donuts | 1 + `builder.py` | Backend change |
| Dashboard tiles + donut | 1 | |
| Child detail tabs | 2 | |
| Parent home progress bars | 1 | |
| **Total** | **≈11 templates, 2 backend touches** | |

### Should the design system be adjusted globally?

**No.** Colour, radius, shadow, badges, buttons and icons all match. Two
global questions only:

1. **Typeface** — adopt a self-hosted geometric sans, or accept `system-ui`?
   A client decision, not a technical one.
2. **Density** — the mockups are denser than every redesign brief asked for.
   This needs an explicit ruling: match the mockups, or keep the calmer
   product and record the deviation against §21.15.

Everything else is targeted, screen-by-screen work.

### Targeted redesign vs global rework

**Targeted.** The tokens are right; the layouts are not. Nine of the eleven
templates above need structural changes that share no common cause beyond
the top bar.

---

## Two things this audit cannot settle

**The density question is a product decision, not a defect.** Every
checkpoint brief in this redesign asked for calm, whitespace, "not an
enterprise table", "not a spreadsheet". The mockups are dense enterprise
screens. The implementation followed the briefs. §21.15 points at the
mockups. Somebody has to choose, and it should not be inferred from a
tie-break.

**The assessment matrix needs a backend decision first.** The single-domain
constraint was reported and approved during that checkpoint — but as an
implementation limit, not as a deliberate deviation from an approved design.
If the matrix is required for acceptance, the selector and save contract
have to change before any pixel does.

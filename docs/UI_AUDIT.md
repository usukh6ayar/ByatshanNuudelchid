# UI audit — before the presentation-layer redesign

Written 2026-08-16, on branch `feat/ui-redesign`, before any CSS or template
was edited. Authority for the work it proposes: [`docs/STACK_DECISION.md`](STACK_DECISION.md)
(Option C — keep the application, replace the presentation layer).

Scope of the audit is the presentation layer only. No model, service,
selector, permission or URL is proposed for change.

---

## 1. Existing template architecture

71 templates under `templates/`, resolved through `DIRS` plus `APP_DIRS`.
There is no `templates/` directory inside any app — every file lives in the
project-level tree, one directory per app.

### Layouts

Five shells at the root, one per audience:

| File | Used by | Strapline (this is load-bearing — see §10) |
|---|---|---|
| `base_teacher.html` | teacher screens | `Багшийн хэсэг` |
| `base_parent.html` | guardian screens | `Эцэг эхийн хэсэг` |
| `base_admin.html` | administrator screens | `Админ систем` |
| `base_auth.html` | login, reset, activation | — |
| `base_error.html` | 400/403/404/500 | — |

The three application shells are near-identical in structure: `.shell` →
`aside.sidebar` (brand, nav, theme switch) + `main.main` (topbar, messages,
content block). They differ only in nav entries and strapline.

**The shell is chosen per request, not per URL.** `apps/core/layouts.py`
exposes `layout_for(user, guardian_view=...)`, and shared screens — the
portfolio, observations, assessment, reports — extend a `base_template`
context variable rather than a literal. This is a genuinely good piece of
design and the redesign must preserve it: the portfolio is one artifact a
teacher and a guardian both open, and the chrome follows the reader.

### Blocks

Every shell exposes the same four: `title`, `heading`, `lede`, `content`.
`base_teacher.html` adds `sidebar_foot`. The contract is consistent, so
retheming the shells does not touch the 60+ templates that extend them.

### Partials

Only three, all root-level: `_icons.html` (an SVG sprite of 15 `<symbol>`s),
`_theme.html` (the switch), `_theme_head.html` (the pre-paint script).

**There is no `components/` directory.** Repeated structures — the child
switcher, the stat tile, the feed row, the meter — exist as CSS classes that
each template hand-writes the markup for. That is the single largest
structural gap and the main thing this redesign should fix.

## 2. Existing reusable elements

Everything reusable today is a CSS class in `static/css/app.css` (669 lines),
with the markup repeated per template:

| Pattern | Class | Where it repeats |
|---|---|---|
| Panel | `.card`, `.card__head` | ~40 templates |
| Statistic | `.tile` + `.tile--blue/green/amber/sky/pink/teal` | both dashboards, portfolio |
| List row | `.feed`, `.feed__item`, `.feed__title`, `.feed__meta` | dashboards, review queue |
| Progress bar | `.meter`, `.meter-list` | dashboard, assessment |
| Person | `.person`, `.avatar` (`--sm`/`--lg`) | lists, dashboards |
| Child switcher | `.switcher` | parent home, dashboard birthdays |
| Shortcut grid | `.quick` | parent home |
| Hero | `.hero`, `.hero__photo`, `.hero__body` | teacher child detail |
| Facts | `dl.facts`, `dl.facts--cols` | child detail, portfolio, parent |
| Table | `.table-wrap` + bare `<table>` | lists, grids, history |
| Term track | `.track` | teacher dashboard |
| Badge | `.badge--ok/warn/muted/brand` | everywhere |
| Buttons | `.btn`, `.btn--ghost`, `.btn--sm`, `.btn-row` | everywhere |
| Empty state | `.empty` | feeds |
| Auth | `.tabs`, `.tab`, `.auth-error`, `.rules`, `.links` | login flow |

The vocabulary is good. What is missing is that it is **only** a vocabulary —
there are no includes, so a change to the shape of a feed row means editing
every template that draws one.

**JavaScript:** two inline blocks, both theme-related, ~15 lines total. No
`<script src=…>` anywhere. No build step. No CDN. (ROADMAP §4 claimed HTMX +
Alpine until 2026-08-16; corrected there.)

## 3. Current UI problems

Ranked by how much they cost at the checkpoint.

1. **No mobile navigation pattern.** Under 900px the sidebar becomes a
   horizontally scrolling strip of nav links pinned above the content. It
   works and it meets the 44px target, but it is a desktop sidebar folded
   flat — precisely the "shrink the desktop layout" the brief rules out. The
   parent experience is meant to be mobile-first and currently is not.
2. **Inline styles as a layout escape hatch.** `style="display:flex; gap:16px"`,
   `style="margin-bottom:8px"`, `style="font-size:.9rem; margin:18px 0 8px"`
   appear across the dashboard, parent home and parent detail. Each is a
   place the design system had no answer, and they are why spacing is
   inconsistent between screens.
3. **No type scale.** Font sizes are written ad hoc at the point of use —
   `.9rem`, `.91rem`, `.92rem`, `.84rem`, `.79rem`, `.78rem`, `1.05rem`,
   `1.3rem`, `1.65rem`. Nine sizes where five would do, and no named steps,
   so nothing enforces that a card title on one screen matches a card title
   on another.
4. **No spacing scale.** Padding and gaps are literals: 18px, 16px, 15px,
   14px, 13px, 11px, 10px, 8px. Visually close enough to look accidental
   rather than rhythmic.
5. **The parent child profile is the weakest screen in the product.** It is
   two cards: a photo beside a definition list, and an enrolment-history
   table. It reads as a database record. §12 of the brief calls this the
   highest visual priority and asks it to say "this is my child's story";
   today it says "row 4 of table `children_child`".
6. **Everything is a card.** The teacher dashboard is 4 tiles + 7 cards
   stacked; the parent home is 2 cards side by side. There are no flat
   sections, so nothing is emphasised — a uniform grid of bordered white
   rectangles gives the eye no entry point.
7. **The `.hero` pattern exists but only the teacher uses it.** The parent's
   view of their own child uses a 96px round avatar in a generic card, while
   the teacher gets a 132px rounded-rectangle hero. That is backwards for a
   product whose emotional centre is the family's view.
8. **No page-level PDF affordance on the parent profile.** `reports:request`
   accepts guardians (verified in `apps/reports/views.py` — `_context` uses
   `child_detail` + `is_guardian_of`), but the child profile does not link
   it. It is only reachable from the home screen's shortcut grid.
9. **Background wash is doing too much work.** Four fixed radial gradients
   behind every page. It reads as warmth on an empty screen and as noise
   behind a dense one.
10. **`.empty` is one treatment for every empty state** — 40px of padding, a
    grey icon, one line. No distinction between "nothing yet" and "nothing
    matched your filter".

**What is already right and must not regress:** the 16px form-control floor,
`.table-wrap { overflow-x: auto; min-width: 0; }`, 44px touch targets under
900px, `dl.facts` stacking under 560px, `clamp()` on the activation code,
the icon sprite, the opt-in dark theme, and the per-request layout resolution.
Every one of those was a defect found by hand and fixed; §10 lists the tests
that hold them.

## 4. Mockup visual system

Read from the images themselves, not from filenames: `parent-home.jpeg`,
`teacher-dashboard.jpeg`, `teacher-child-profile-360.jpeg`,
`overview-mobile-app-screens.jpeg`.

**Structure.** Fixed white left sidebar (~240px) with a tinted rounded-square
logo tile; a wide content area on a warm off-white ground; a top row with page
title left and identity pill right. Content is a 2- or 3-column grid of white
panels. Panel header is always `title left / "Бүгдийг харах" link right`.

**Shape.** Panels ~16–20px radius, 1px hairline border, shadow so faint it
reads as a border. Inner tiles ~12–14px. Pills fully round. Icons sit in a
44px tinted rounded square, one hue per statistic.

**Colour.** Neutral ground with a violet primary (`#6C63FF`-family) for
navigation state, primary buttons and links. Statistics carry six pastel
tints — blue, green, amber, sky, pink, teal — each as a soft background with
a saturated icon. Colour is used to make a tile findable by hue before it is
read; it is never decoration.

**Typography.** One geometric sans throughout, tight tracking on large
headings. Clear steps: page title ~24px/700, panel title ~16px/600, body
~14px, meta ~12px muted, numerals large (~28px/700) in statistic tiles.

**Child presentation.** The 360° screen leads with a large rounded-rectangle
photograph (~130px) beside the name, a status pill, and registration facts in
a label-above-value grid spanning the full width. Below that, a tab strip,
then sectioned panels: recent activity as a dated list with thumbnails, a
birthday timeline with photo strips, guardians with contact actions.

**Mobile** (`overview-mobile-app-screens.jpeg`). A violet header card
carrying greeting and the child, a 3-column grid of tinted icon tiles as the
primary navigation, content as a vertical list, and a **fixed bottom
navigation bar of 4–5 items with a raised primary action**. This is a
deliberately different layout, not a narrowed desktop.

**Density.** Generous. Panels breathe; there is real whitespace between
groups; nothing is edge to edge.

## 5. Gap between current UI and the mockups

| Dimension | Current | Mockup | Gap |
|---|---|---|---|
| Shell | white sidebar + topbar | same | **small** — structurally already right |
| Panel shape | 18px radius, hairline, faint shadow | 16–20px, hairline, faint shadow | **none** |
| Statistic tiles | six tints, icon in tinted square | same | **none** |
| Palette | `#f6f7fb` ground, `#5b4bd6` brand | warmer `#FAF9F6`, `#6C63FF` | **small** — retune tokens |
| Type | 9 ad-hoc sizes, system font | 5 clear steps | **medium** — needs a scale |
| Spacing | literals, 8 values | consistent rhythm | **medium** — needs a scale |
| Mobile nav | folded sidebar strip | bottom bar + tile grid | **large** |
| Child profile | photo + `dl` + table | hero, sections, timeline, thumbnails | **large** |
| Parent identity | generic, same chrome as teacher | warm, child-led | **large** |
| Components | CSS classes, markup repeated | — | **large** (structural) |
| Charts | bar meters | donut + radar + line | **deliberate divergence — see below** |

**Where the mockups are deliberately not followed.** The client's dashboard
draws attendance, health flags, meals, payments, growth curves, survey
progress, a donut and a radar chart. Those are Phase 2 and 3 (see
`docs/design/INDEX.md`), and the brief's §13 explicitly forbids radar charts,
analytics panels and fake metrics. Where the image and the brief conflict,
**the brief wins**: take spacing, colour, shape and typography from the image;
take content from what `selectors.teacher_dashboard()` actually returns. The
existing template already made this call correctly — a bar per domain instead
of the donut — and the redesign keeps it.

Same for the parent home: its drawn right rail is Ирц / Эрүүл мэнд / Хоол /
Төлбөр / Судалгаа, all deferred. `docs/design/INDEX.md` already records the
Phase-1 subset — child switcher, child card, teacher feed, announcements,
domain progress, portfolio link — and that is the list used.

## 6. Proposed design system

### Tokens

Retune the light palette toward the brief's §7 direction and re-tune dark in
the same pass, so the theme is never half-migrated:

```
--bg      #faf9f6   warm off-white ground (was #f6f7fb, cool)
--card    #ffffff
--line    #ece9e4   warm hairline (was #e6e8ef, cool)
--brand   #6c63ff
--ink     #25232a
--muted   #817e8a
```

Accent tints stay six, retuned toward the brief's mint / sky / warm-yellow /
peach. Ratio held at roughly 80% neutral / 20% accent.

### Type scale

Five named steps replacing nine ad-hoc sizes:

```
--t-page   1.5rem/700     page title
--t-title  1.05rem/650    panel and card title
--t-body   0.94rem/400    body
--t-meta   0.8rem/400     secondary and metadata
--t-label  0.78rem/600    labels, badges, table headers
--t-stat   1.75rem/700    numerals in statistic tiles
```

Line height 1.5 on body and **1.35 on headings** — Mongolian compounds
(`Хөгжлийн үнэлгээний явц`, `Бүртгэлийн дугаар`) are long and wrap often, so
headings must survive two lines without colliding.

Font: keep the system stack. It renders Cyrillic correctly on every target
platform, costs no request, and adds no build step. A webfont would mean
either a CDN (ruled out) or self-hosting ~200KB for the same glyphs.

### Spacing scale

`--s1: 4px · --s2: 8px · --s3: 12px · --s4: 16px · --s5: 24px · --s6: 32px`.
Every new padding, gap and margin comes from these.

### Components to build (only what the two screens need)

As Django includes under `templates/components/`, each taking explicit
context via `{% include with %}`:

- `page_header.html` — title, lede, optional actions
- `stat.html` — one statistic tile
- `section.html` — a flat titled section with an optional trailing link
- `feed_item.html` — avatar/icon + title + meta, optionally a link
- `empty.html` — icon, message, optional action
- `child_switcher.html` — the §2.3 switcher
- `avatar.html` — photo or initial, three sizes
- `meter.html` — one labelled progress bar
- `bottom_nav.html` — mobile bar, parent shell only

Not built: modal, toast, tabs, skeleton, dropdown, pagination, uploader.
Nothing in the two checkpoint screens needs them, and a component with no
caller is a guess.

## 7. Proposed implementation order

1. Tokens, type scale, spacing scale in `app.css` — both themes together
2. Component partials + the shared shells (parent gets bottom nav)
3. **Parent child profile / portfolio** — mobile-first, 375/390 first
4. **Teacher dashboard** — desktop-first, verified down to 375
5. Full test suite, then stop for approval

Run `make test-fast` after step 1 and after each of 3 and 4, so a failure
points at one change rather than five.

## 8. Templates reusable structurally

Keep as-is; they inherit the new tokens for free and need no edit:

- all five shells keep their filenames and block contract (§10 requires it)
- `_icons.html`, `_theme.html`, `_theme_head.html`
- the whole `accounts/` auth flow — 14 templates, already mockup-derived
- `reports/child_portfolio.html`, `reports/term_report.html`,
  `reports/spike.html` — **print only**; WeasyPrint renders these to A4 and
  they must not inherit screen chrome
- `admin/base_site.html`
- error pages

## 9. Templates that should be redesigned

In checkpoint scope now:

- `children/parent/detail.html` — the child profile, rebuilt
- `dashboard/teacher.html` — rebuilt
- `base_parent.html`, `base_teacher.html` — retheme + parent mobile nav

Proposed next, **not** in this checkpoint:

1. `children/parent/home.html` — should follow the new profile immediately
2. `observations/form.html` — highest-frequency teacher workflow; the brief
   §14 asks for five grouped sections and it is currently one flat form
3. `children/teacher/list.html` + `children/teacher/detail.html`
4. `portfolio/overview.html` — the age 2–5 pages
5. `assessment/group_grid.html` — the widest table in the app
6. `comms/`, `reports/request.html`, `accounts/profile.html`
7. `base_admin.html` + `dashboard/admin.html`

## 10. Risks

**The test suite constrains the CSS and templates in ways that are not
obvious.** These are hard constraints, verified by reading the tests:

| Constraint | Test |
|---|---|
| Literal string `.table-wrap { overflow-x: auto; min-width: 0; }` must appear in `app.css`, on one line | `test_responsive.py` |
| First `}`-terminated block after `input[type=text]` must contain `font-size: 16px` | `test_responsive.py` |
| Layout filenames are hardcoded: `base_teacher/parent/auth/error.html` at `templates/` root — **do not create `templates/layouts/`** | `test_responsive.py`, `test_theme.py` |
| Exactly one strapline per rendered page — a shared partial must never carry another shell's strapline | `test_layouts.py` |
| `prefers-color-scheme` must not appear in the CSS | `test_theme.py` |
| The `:root[data-theme="dark"]` block must override `--ink --bg --card --line --muted` | `test_theme.py` |
| `{% include "_theme_head.html" %}` inside `<head>`; `{% include "_theme.html" %}` in both shells | `test_theme.py` |
| Every `<use href="#i-…">` needs a `<symbol>` with a `viewBox` | `test_icons.py` |
| No multi-line `{# … #}` comments; every template compiles | `test_templates.py` |
| Every `<table>` outside the three print templates needs `.table-wrap` | `test_responsive.py` |

**Other risks:**

- **N+1 on the redesigned profile.** Adding recent observations, media and
  portfolio sections turns a 4-query page into a many-query one. Each
  selector call must be checked, and photos must be reached through the
  observations already fetched.
- **Photo visibility is a §21.3 boundary, not a layout choice.** Recent
  photos must come from observations the guardian may read —
  `child_observations()` already enforces `visible_to_parents=True AND
  review_status=APPROVED`. Building a gallery from `MediaFile.objects`
  filtered by child would bypass that gate and leak images from observations
  a teacher marked private. This is the single most dangerous mistake
  available in this redesign.
- **Dark theme drifting.** Retuning light tokens without dark in the same
  commit produces dark text on dark panels — the most likely visible defect
  at the checkpoint.
- **Regressing a hand-found mobile fix.** The five defects fixed on Day 10
  (16px controls, `min-width: 0`, `dl.facts` stacking, `clamp()` on the code,
  44px nav) were each found by inspection at 375px. Tests hold three; the
  other two are not tested and could be lost in a rewrite.
- **Scope creep across 71 templates.** Retuning shared tokens changes every
  screen at once. The two checkpoint screens are rebuilt; the rest inherit
  new colours and spacing without being re-laid-out, so some will look
  transitional until their turn. That is expected and is why the checkpoint
  exists.
- **No real device.** Every width below is checked by CSS reasoning and
  breakpoint review, not by holding a phone. The ROADMAP §16 row for real
  devices stays ⬜ and this redesign does not close it.

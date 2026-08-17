# Phase 1 UI/UX map

**Date:** 2026-08-17 · **Branch:** `feat/ui-redesign` · **Status:** for approval, nothing implemented

Supersedes the mockup-fidelity direction of the same day. The client's
mockups return to being a *visual reference*; they are no longer the layout
acceptance target for Phase 1.

**Direction:** clean · simple · modern · warm · fast —
"modern calm SaaS + private child portfolio".

**Core principle:** one screen, one primary job.

---

## 0. What this changes

The mockup-fidelity audit produced a P0 to rebuild the assessment screen as a
children × 9-domain matrix. **That is now cancelled.** Assessment stays one
domain at a time, which is what the backend does and what the current screen
already implements.

Backend work started on that matrix has been reverted:
`apps/assessment/{selectors,services,views}.py` are back to their approved
state, assessment tests pass, ruff clean. The redesigned
`templates/assessment/group_grid.html` from the approved checkpoint is
untouched.

**Net effect: most of this map is already built.** The gaps are listed in §7.

---

## 1. Design tokens

The specified palette is within a few points of what is already in
`app.css` — no visual re-tune needed, but the exact values should be adopted
so the source of truth is unambiguous.

| Token | Specified | Current | Action |
|---|---|---|---|
| Background | `#F8F7F4` | `#faf9f6` | Adopt |
| Surface | `#FFFFFF` | `#ffffff` | — |
| Primary | `#6C63FF` | `#6c63ff` | — |
| Text | `#26242B` | `#25232a` | Adopt |
| Muted | `#77737D` | `#817e8a` | Adopt |
| Border | `#E9E6E0` | `#ece9e4` | Adopt |
| Accents | mint · soft blue · soft yellow · soft peach | same four | — |
| Radius | 14–18px | 12–18px | Adopt 14 as the small step |
| Interactive | ≥44px | ≥44px | — already enforced and tested |
| **Inputs** | **≥48px** | **~42px** | **Change** — one rule in `app.css` |

Everything else — shadows, spacing scale, type scale, badges, buttons —
already matches the brief's description.

---

## 2. Navigation

### Teacher — specified

`Dashboard · Children · Observations · Assessment · Portfolio · Reports`
(+ profile, which exists)

### ⚠️ Four of these six have no teacher-level route

This is the one genuine blocker in the map and it needs a decision before
any nav work starts. Every route below is real; the problem is what a
top-level menu item would link to.

| Nav item | Existing route | Scope | Usable as a menu item? |
|---|---|---|---|
| Dashboard | `dashboard:teacher` | teacher | ✅ yes |
| Children | `children:list` | teacher | ✅ yes |
| Observations | `observations:review_queue` | teacher | ✅ yes — but it is the *parent-submission review queue*, not "all observations" |
| Assessment | `assessment:group_grid` | **group** | ⚠️ needs a group id; a teacher may hold several |
| Portfolio | `portfolio:overview` | **child** | ❌ no child-independent route exists |
| Reports | `reports:request` | **child** | ❌ no child-independent route exists |

**Three options, in order of preference:**

| Option | Nav | Cost |
|---|---|---|
| **A — build the nav from what exists** | Dashboard · Children · Ажиглалт хянах · Үнэлгээ · Мэдэгдэл · Профайл | Zero new screens. "Үнэлгээ" links to the teacher's group; if they hold more than one, it goes to a small chooser |
| B — add two thin index screens | Full six as specified | Two new views + templates ("pick a child, then portfolio / report") |
| C — keep the current five-item nav | as built today | Zero |

**Recommendation: A.** It reaches every Phase 1 capability, invents no
screens, and Portfolio and Reports stay where users actually reach them —
from a child.

### Parent — specified

`Home · Portfolio · Notifications`

Same issue, smaller: Portfolio is child-scoped. For a guardian with one
child — the common case — the shell can resolve it. With two, the child
switcher on Home already decides.

**Recommendation:** Home · Portfolio (resolved from the selected child) ·
Notifications. Profile and logout stay in the header, not the bar.

Current parent bottom bar is `Нүүр · Мэдэгдэл · Бүртгэл` — this replaces
`Бүртгэл` with `Портфолио` and moves profile to the header.

---

## 3. Screen map — teacher

| Screen | Primary job | Primary CTA | Main sections | Desktop | Mobile |
|---|---|---|---|---|---|
| **Dashboard** | Know what needs attention | Ажиглалт нэмэх | Greeting + date · 3 summary items (children, recent observations, pending assessments) · recent observations · quick actions | One column, summary row of 3 | Stacked; summary 3-across |
| **Children** | Find a child | Хүүхэд нэмэх | Search · compact list | Compact rows: photo, name, age, group, status | Tappable cards |
| **Child detail** | Understand / work on this child | Ажиглалт нэмэх | Identity · actions · recent observations · assessment summary · portfolio link · guardians | Two columns: record + reference | One column |
| **Observation form** | Record an observation | Хадгалах | Child · date/type · what happened · child action · child words · development area · assessment · visibility · photo | One column, section headings | Same |
| **Observation list** | Review a child's observations | Ажиглалт нэмэх | Filters (collapsed) · list | Rows | Cards |
| **Assessment** | Assess a group fast | Бүгдийг хадгалах | Group · term · **domain** · child rows with `[1][2][3][4]` | Rows with chips right | Chips wrap under name |
| **Portfolio** | Navigate the child's record | — (hub) | Identity · About Me · ages 2–5 · birthday · PDF | One column | Same |
| **Reports** | Generate a PDF | PDF үүсгэх | Child · type · sections · generate | One column | Same |

## 4. Screen map — parent

| Screen | Primary job | Primary CTA | Main sections | Desktop | Mobile |
|---|---|---|---|---|---|
| **Home** | See what happened recently | — | Greeting · child card · notifications · recent moments · recent observations · quick links | One column, 1000px cap | Stacked, bottom bar |
| **Child detail** | "My child's story" | Хувийн хавтас | Large photo · name · age · About Me · recent moments · ages 2–5 · development · PDF | One column | Photo centred, stacked |
| **Portfolio** | Explore the story | — (hub) | Identity · About Me · ages 2–5 · birthday · PDF | One column | Same |
| **Notifications** | Read what was sent | — | Unread ● / read ○ · title · preview · date | List | Compact list |
| **Notification detail** | Read one notice | — | Title · date · sender · body · attachment | Measured column | Same |

---

## 5. Assessment — confirmed shape

**One domain at a time.** Group + term + domain selectors, then one row per
child with four level chips.

This is exactly what is built and tested today. **No work required.**

The matrix is explicitly out of Phase 1 and would need a new selector, a
widened save contract and a mobile strategy — none of which is being spent.

---

## 6. What already matches this brief

Built, tested, and consistent with the direction — **no rework**:

- Design tokens, spacing, type scale, badges, buttons, icons
- Teacher dashboard (3 quick actions, 4 stat tiles, recent observations, no charts)
- Children list (compact rows desktop / cards mobile, search, `Хүүхэд нэмэх`)
- Teacher child detail (identity, actions, observations, assessment, guardians)
- Observation form (sections, one page, visibility, photo)
- Observation list, assessment grid, portfolio overview
- Notifications list + detail (unread dot + word, no feed UI)
- Reports request + status
- Parent home, parent child detail
- Responsive at all five widths, 44px targets, zero overflow
- Security, permissions, media, Celery, WeasyPrint, 932 tests

---

## 7. Gaps against this brief

Ordered by effort, smallest first.

| # | Gap | Where | Effort |
|---|---|---|---|
| 1 | Input height 42px → **48px** | `app.css`, one rule | XS |
| 2 | Adopt the four exact token values | `app.css` | XS |
| 3 | Dashboard shows **4** summary tiles; brief says **3** (children, recent observations, pending assessments) | `dashboard/teacher.html` | XS |
| 4 | Parent bottom bar: replace `Бүртгэл` with `Портфолио`, move profile to header | `base_parent.html`, `bottom_nav.html` | S |
| 5 | Teacher nav rename/reorder per option A | `base_teacher.html` | S |
| 6 | Parent home has **no development progress section** — assessment data exists and the brief lists it under parent child detail | `children/parent/home.html` or `detail.html` | S |
| 7 | Teacher nav "Үнэлгээ" needs a group; chooser required if a teacher holds several | `base_teacher.html` + possibly one small view | M — **needs the §2 decision** |
| 8 | Observation form uses five numbered section cards; brief says "not five large cards — headings and whitespace" | `observations/form.html` | M |

**Not in this list on purpose:** the assessment matrix, the teacher top bar,
child-detail tabs, the report preview, and PDF donut charts. All were
mockup-fidelity items and are now out of scope.

---

## 8. Proposed checkpoint order

Small and verifiable, one at a time, stopping after each:

1. **Tokens + inputs + dashboard tiles** (gaps 1–3) — one CSS pass, one template
2. **Navigation** (gaps 4, 5, 7) — after the §2 decision
3. **Parent development section** (gap 6)
4. **Observation form density** (gap 8)

Each with: full pytest · ruff · `makemigrations --check` · responsive probe at
375 / 390 / 768 / 1024 / 1440.

---

## 9. Decisions needed before implementation

1. **Teacher navigation** — option A, B or C from §2? Portfolio and Reports
   have no child-independent route, so the six-item menu as literally
   specified cannot be built without inventing two screens.
2. **"Үнэлгээ" for a multi-group teacher** — link to the first group, or add
   a chooser?
3. **Parent development progress** — on Home, on child detail, or both? The
   brief lists it under parent child detail; the audit found it drawn on the
   Home mockup.
4. **Dashboard tiles: drop from 4 to 3?** The fourth is "birthdays today",
   which is real §12.1 data and cheap to keep.

Nothing is implemented. Awaiting approval.

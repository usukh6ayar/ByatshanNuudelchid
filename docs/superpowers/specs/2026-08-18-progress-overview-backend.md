# Progress overview & monthly note targets — backend spec

**Status:** written 2026-08-18, not yet built. Frontend shell already merged
(placeholders below) on `templates/assessment/group_grid.html` ("Явцын
үнэлгээ"); this document is what a backend developer needs to fill them in.

Not tied to any RFP §. It mirrors a feature in the client's own Flask
reference prototype (`quick_assess.html`, "Төлөвлөлтийн тойм" /
"Сарын норм") that the client wants ported, but nothing in `Project_Info.md`
requires it and it is not listed in `ROADMAP.md`. Treat it as a
client-requested enhancement to prioritize, not an acceptance criterion —
confirm which phase it belongs in before starting (CLAUDE.md §7.1).

---

## 1. Why three pieces are blocked

`templates/assessment/group_grid.html` already renders, with real data and
no new backend:

- the group/domain/term identity bar,
- the "Хүүхэд сонгох" search + select,
- the "Тэмдэглэлийн төрөл" tiles,
- a **band track** (Бага/Дунд/Ахлах/Бэлтгэл бүлэг timeline), computed
  entirely from `Group.age_band` and `Group.school_year.starts_on` — both
  already in the view's context, no new field or query needed,
- the existing one-domain assessment grid (`Assessment`, `AssessmentLevel`).

Three more pieces from the client's mockup have **no supporting data
anywhere in the codebase** — confirmed by a full-repo search, not an
oversight:

1. No field or table stores a "notes per child per month" target. Not on
   `Group`, not on `Kindergarten`, not a standalone config table.
2. No selector groups `Observation` rows by month/quarter/year for a group.
   `apps/observations/selectors.py:child_observations()` returns one
   child's queryset, filterable by `date_from`/`date_to`, but nothing
   aggregates it across a group or buckets it by calendar month — no use of
   `TruncMonth`/`TruncQuarter`/`TruncYear` exists in `apps/` today.
3. Consequently nothing can compute "who has the fewest notes this year"
   (the recommended-child card) or a per-month completion percentage.

These three need a model field (or table), a selector, and the view context
wired up — all backend. The frontend author (this session) works
frontend-only and cannot write them; hence this handoff.

## 2. Data model

```
ObservationNorm   TenantScopedModel
    group          FK -> Group
    school_year    FK -> SchoolYear
    monthly_target PositiveSmallIntegerField, choices 1-5, default 2
    ⚠ unique(group, school_year) where deleted_at IS NULL
```

A table, not a field on `Group` — CLAUDE.md §2.3: this is a number a
teacher/admin edits per group per year, and a group's target this year says
nothing about its target next year. `services.py` needs one function:

```python
def set_monthly_target(*, actor, group, school_year, target: int) -> ObservationNorm:
    ...  # get_or_create + update, audit-logged like any other write
```

No migration touches `Observation` itself — the target is a separate
number compared against a count, not a column on every note.

## 3. Selectors (`apps/assessment/selectors.py`, next to `group_grid`)

```python
def monthly_progress(user, group, school_year) -> dict:
    """One row per calendar month the school year covers (Сар), each with
    the group's children bucketed by whether they reached the month's
    target. Powers the "Сараар" tab.

    Returns:
        {
          "target": int,                       # ObservationNorm.monthly_target, or the default
          "months": [
              {
                "month": date(2025, 9, 1),
                "label": "9-р сар",
                "total_children": int,
                "met": int,                     # children with count >= target this month
                "remaining": int,                # total_children - met
                "observations": [                 # for the detail/expanded view
                    {"child": Child, "type": ObservationType, "sud_hint": str|None,
                     "excerpt": str, "date": date},
                    ...
                ],
              },
              ...
          ],
        }
    """

def quarterly_progress(user, group, school_year) -> dict: ...  # same shape, TruncQuarter

def yearly_progress(user, group, school_year) -> dict:
    """One bucket for the whole year. Same per-bucket shape as the month/
    quarter selectors above, plus two figures the client's mockup shows
    only at this granularity:

    Returns:
        {
          "target": int, "total_children": int, "met": int, "remaining": int,
          "pct": int,                     # met / total_children, 0-100
          "avg_per_child": float,         # total observations / total_children
        }
    """

def recommended_children(user, group, school_year, limit=5) -> list[dict]:
    """Re-checked against the reference's own template
    (teacher/quick_assess.html:184-198): `annual_plan.low_children` is a
    **list**, not a single child — every child in the group below target,
    lowest count first, each with its own "Сонгох" action that jumps to
    that child's note-type tiles. Do not build this as a single
    recommended child; the UI needs the whole list (a `<details>`
    disclosure titled with the count, exactly like `group_grid.html`'s
    existing "Хүүхэд сонгох" pattern — reuse that component instead of
    inventing a second one).

    Returns: [{"child": Child, "count_this_year": int, "target": int,
               "status": "low"|"good"}, ...] — empty list if everyone in
    the group has met target.
    """
```

Group by `TruncMonth("observed_at")` (or whichever field is the record's
timestamp — check `Observation`'s actual date field name) filtered to
`enrollment__group=group, enrollment__school_year=school_year`, restricted
through `visible_children(user)` exactly like `group_grid()` already does.
`recommended_child` is one `annotate(count=Count(...))` + `order_by("count")`
+ `first()` over the same queryset.

## 4. View wiring (`apps/assessment/views.py`, `group_grid`)

Add a `tab` GET param (`month` default, `quarter`, `year`, `recent`) and
call the matching selector; pass `norm`, `recommended` into context
alongside the existing `rows`/`levels`/`missing`/`total`. `recent` is a
simple `child_observations`-style query across the group ordered by
`-observed_at`, limited to N — no new selector needed for that tab, reuse
`Observation.objects.filter(...)` the way `group_grid()` already builds
`enrollments`.

## 5. What the frontend already expects

`group_grid.html` has three sections marked with an `icon="soon"` empty
state — search for `components/empty.html` with `message` ending in
"удахгүй нэмэгдэнэ" to find them. Once the above lands, replace each with
real markup driven by the new context keys. The client's mockup text for
each (kept verbatim, Mongolian, since it is what ships in the UI):

**Норм тохиргоо** — under the band track: a read-only "2025 - 2026 оны
хичээлийн жил" indicator plus a `<select>` for
"Сард нэг хүүхдэд орох тэмдэглэлийн тоо" (1–5), posting to
`set_monthly_target`.

**Санал болгох хүүхэд** — "Санал болгох хүүхдийн жагсаалт" + count badge,
a `<details>` disclosure (reuse the existing "Хүүхэд сонгох" markup
pattern already in `group_grid.html`). One row per child returned by
`recommended_children()`: child's name, "Энэ жил {count_this_year}
тэмдэглэлтэй. Зорилт: {target}.", a "Сонгох" button that does what the
existing `pickFirstVisibleFocusChild()`-adjacent pattern already does —
set `focus_child` and jump to the note-type tiles for that child (the
reference's own `pickChildFromProgress()` sets the dropdown then
scroll-jumps; same idea, this app's version can just be a link with
`?focus_child=<id>`).

**Ахиц** — four tabs: Сараар (default), Улирлаар, Жилээр,
"Сүүлд хийсэн" (a plain recent-observations list, no target math). The
"Тайлан харах" link is **already wired** (2026-08-18) — it points at the
selected child's existing per-child report request page
(`reports:request`, RFP §549), since no group-wide analytics report
exists in this app (the reference's own link goes to a
`teacher_analytics` dashboard this project never built and is not
scoped to build here — do not add one for this). Below the tabs, one
card per month/quarter/year:

```
9-р сар          0/1 хүүхэд · 1 үлдсэн · зорилт 2
[empty state: "Энэ сард тэмдэглэл ороогүй байна"]

2-р сар          50% (1/2)
  Од — Ажиглалт — ХЭМ2.1в · Ok — "Дахин давтаж бататгах шаардлагатай." — 02/06
```

The `ХЭМ2.1в` code is the same СҮД lookup already wired into
`observations/list.html`'s "Холбогдох СҮД" hint — if `Observation` still
has no `sud_code` column when this is built, show the note without a code
rather than reviving the auto-write behavior the client explicitly
rejected earlier in this project (see the "Холбогдох СҮД" hint on
`observations/list.html` for why).

## 6. Testing

New views/selectors touching child data need the standard three
(CLAUDE.md §4.1): a teacher from another group, a guardian of another
child, a user from another kindergarten — each must 404 on the new tab
query params exactly as they do on the existing grid.

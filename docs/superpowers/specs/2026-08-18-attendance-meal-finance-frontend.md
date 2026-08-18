# Attendance / meal / finance — frontend integration spec

**Status:** written 2026-08-18, not yet built. Written from the frontend side
against the already-assessed `docs/FINANCE_SCOPE.md` — read that document
first; this one adds nothing to the phase/scope decision, it only maps the
client's own role × screen table onto what exists in code today versus what
still needs a backend developer.

The client's own message (verbatim structure, kept because it is the
correct shape for these screens):

```
Багш: Ирц + хоол бүртгэнэ
  → Систем: ирсэн өдөр, хооллосон өдрийг нэгтгэнэ
  → Удирдлага/нягтлан: тариф, дүрмээр санхүүжилт ба invoice тооцно
  → Эцэг эх: зөвхөн өөрийн хүүхдийн invoice, үлдэгдэл, төлбөрийг харж төлнө
```

## 1. What already exists vs what is still missing

| Piece | State | Where |
|---|---|---|
| `Attendance` model, services, selectors | **Built, tested (18 tests)** | `apps/attendance/` |
| Accountant role + finance permission axis | **Built, tested** | `Role.ACCOUNTANT` (`apps/accounts/models.py`), `finance_kindergartens`/`can_view_finance`/`can_manage_finance`/`can_view_child_finance` (`apps/core/permissions.py`) |
| Attendance **views/urls/templates** | **Nothing.** No `apps/attendance/views.py`, no `urls.py`, zero web-reachable page | — |
| Accountant **login → landing page** | **Dead end today.** No seed user, no `base_accountant.html`, no dashboard route. An accountant who logs in lands on the guardian "no children" empty page | see §2 |
| Meal register, meal cost | **Nothing** — no model | `нэмэлт.md` §2–3 |
| Funding rules, state funding, monthly calculation | **Nothing** — no model | `нэмэлт.md` §4–6 |
| Invoice, Payment, Tariff | **Nothing** — not even a stub. Only mentioned in a docstring example in `permissions.py` | `нэмэлт.md` §7–8 |
| Financial dashboard, child finance tab, 9 reports | **Nothing** | `нэмэлт.md` §9, §10, §16 |
| `dashboard/teacher.html`'s "Ирц бүртгэх" panel | **Frontend mock-up only** — its own comment says so (line 87: *"Энэ нь frontend бэлтгэл дэлгэц. Одоогоор ирц, хоолны бүртгэл хадгалахгүй."*) | `templates/dashboard/teacher.html:48-88,330-378` |

Two very different situations hide under one client message: **attendance
can be wired to a real, already-tested backend today**; **meal and finance
cannot, because nothing exists under them yet.**

## 2. Fix first: the accountant role is a dead end

Before any "Удирдлага/нягтлангийн хэсэг" screen can be reached at all,
three small backend gaps block it — none of them are the finance engine
itself, all of them are routing:

1. No seed accountant user (`apps/core/management/commands/seed_demo.py`
   has zero "accountant" occurrences) — nothing to log in as.
2. `apps/core/layouts.py:layout_for` doesn't recognize `Role.ACCOUNTANT`,
   so it silently falls through to the **guardian** layout
   (`base_parent.html`).
3. `apps/core/views.py:home`'s post-login redirect doesn't recognize
   `Role.ACCOUNTANT` either, so it falls through to
   `children:parent_home` → renders `no_children.html` — an accountant
   sees an empty "no children" page.

This needs, at minimum: a `base_accountant.html` layout (can start as a
copy of `base_admin.html`'s shell with its own nav), `layout_for` and
`home`'s role dispatch extended for `ACCOUNTANT`, and a seed accountant
user. This is a small, self-contained fix and should land before §5
below, regardless of how much of the finance engine itself gets built.

## 3. Ready today: attendance

`apps/attendance/services.py` and `selectors.py` already do everything a
first attendance screen needs — `record_attendance`, `record_group_day`,
`group_day_sheet`, `child_attendance`, `monthly_status_counts`,
`unmarked_children`. **No new model, service, or selector function is
required** for the three screens below — only a `views.py`, `urls.py`,
and templates that call what's already there. That thin view layer is a
judgment call on the frontend-only boundary (CLAUDE.md §2.1 already wants
views this thin — parse request, call service, return response) — flagging
it rather than writing it, since it's still new Python outside
templates/CSS/JS.

**Багшийн "Өнөөдрийн ирц"** — replaces the mock-up panel in
`dashboard/teacher.html`. One page per group per day:
`group_day_sheet(group, date)` for the roster, a form posting each mark to
`record_group_day`. The mock-up's own status buttons/colors
(`templates/dashboard/teacher.html:330-378`) are reusable groundwork —
they were built to match `AttendanceStatus`'s six values already.

**Эцэг эхийн "Ирц"** — a read-only page on the child's tab: `child_attendance(user, child)`,
permission-checked exactly as every other guardian-facing selector already is.

**Удирдлага/нягтлангийн "Ирцийн нэгтгэл"** — `monthly_status_counts(group=... /
kindergarten=..., year, month)` per §1's table. Reminder from
`apps/attendance/selectors.py`'s own design: this returns counts **per
status**, never a single "funding days" figure — do not collapse
"present + half_day" into one number in the template. That collapsing is
a funding-policy decision (D4 in `FINANCE_SCOPE.md`) explicitly deferred
to the rules engine, which does not exist yet.

## 4. Not ready: meal register

`нэмэлт.md` §2 wants the same shape as attendance — per child, per day,
recorded by the teacher. No `MealRecord` model exists. Once a backend
developer adds one (same pattern as `Attendance`: hangs off `Enrollment`,
`simple_history`, one row per enrollment per day), "Хоол бүртгэх" on the
teacher screen and "Хоол" on the child's parent tab are the same shape of
work as §3 above — flagging now so the frontend pattern is obvious once
the model lands, not asking for anything today.

## 5. Not ready: the whole money chain

Санхүүжилт / Тариф / Invoice / Төлбөр / Санхүүгийн самбар / the 9 reports
— `FINANCE_SCOPE.md` §2–§9 covers this in full: a rules engine, a
five-state calculation lifecycle, an external payment integration, and a
reversal-entry model stricter than CLAUDE.md §3.3's ordinary soft delete
(confirmed financial transactions must never be soft-deleted — a
correction is a new opposite row, not a hidden one). D3 (the real funding
formula) and D4 (what counts as a funding day) are still open per that
document's §9 — building any of this on a guessed formula produces
"confident wrong numbers," in that document's own words.

Once the models exist, the client's screen map becomes:

| Screen | Role | Reads from (once built) |
|---|---|---|
| "Санхүү" (child tab) | Guardian | `can_view_child_finance` + a per-child invoice/balance selector |
| "Санхүүгийн самбар" | Admin/Accountant | `can_view_finance` + a kindergarten-wide finance summary selector |
| "Тариф ба дүрэм" | Admin/Accountant | `can_manage_finance` + the (not yet built) `Tariff` CRUD |
| "Invoice" | Accountant, read-only for guardian | `can_manage_finance` (write) / `can_view_child_finance` (read) |
| "Тайлан" | Admin/Accountant | one of the 9 reports in `нэмэлт.md` §16 |
| "Audit log" | Admin/Accountant only, never teacher/guardian | extends `AuditLog`/`audit()` — per §14, a structured before/after shape is still an open decision (D5) |

Every row already has its permission predicate written and tested
(`apps/core/permissions.py`) — the frontend gate is solved before the
data model that would feed it exists, which is the right order but means
none of these screens can be built yet without inventing fake numbers.

## 6. What this spec is asking for

Nothing today beyond §2 (the three small accountant-routing fixes) and
§3 (a views/urls/templates layer over the already-tested attendance
backend) — both real, both buildable without guessing a funding formula.
Everything in §4 and §5 needs a backend developer to work through
`FINANCE_SCOPE.md` §7's decisions (D1–D8) first.

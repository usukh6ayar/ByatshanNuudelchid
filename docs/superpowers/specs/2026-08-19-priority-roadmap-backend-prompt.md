# Backend priority roadmap — prompt for the backend developer

**Status:** written 2026-08-19. The five-phase order below is the client's
own priority list (their document, kept verbatim as headings). This spec
translates each phase into concrete backend work, grounded in what already
exists in this codebase today — not a re-derivation from the RFP, a mapping
onto real files.

**Audience:** whoever picks up backend work on this project next — human or
agent. This project's frontend author (the session that wrote this document)
works frontend-only per `CLAUDE.md` and has not touched `services.py`,
`selectors.py`, `models.py`, migrations, or `permissions.py` — every
contract below was reverse-engineered from the shipped frontend so the two
sides meet exactly, not approximately. Treat the "frontend contract" section
in each phase as the interface to satisfy, not a suggestion — changing a
field name there means also changing the template that already ships.

**Read `CLAUDE.md` in full before starting.** Every rule in it is mandatory,
not a style guide. The ones that bite hardest on this specific list:
authorization only through `apps/core/permissions.py` (§1.1–§1.3, 404 not
403), business logic in `services.py`/`selectors.py` and never in a view or
Django Admin (§2.1, §2.4), `TenantScopedModel` + soft delete on every new
model (§3.1, §3.3), the three mandatory cross-tenant/cross-role 404 tests on
every new view touching child data (§4.1), and PDF/Excel/bulk work going to
Celery via `transaction.on_commit`, never inline (§6).

---

## 0. A caution worth saying out loud before day one

The client's own RFP (`Project_Info.md`) places real-time parent↔teacher
chat in **"IV үе шат — Ирээдүйн боломжууд,"** explicitly marked **"заавал
хийхгүй"** (not required). `ROADMAP.md` doesn't list messaging in Phase 1,
2, or 3 at all — it isn't deferred, it's simply never mentioned as scope.
This priority document puts it first.

That reordering is the client's call to make, and this document follows it
as given. But `CLAUDE.md` §7.1 is explicit: *"If the user asks for one, it
can be built — but first say which phase it belongs to and ask whether to
pull it forward. Pulling work forward without saying so is how a ten-day
delivery becomes a twenty-day one."* Flagging it here so whoever schedules
this work is deciding with that fact in view, not discovering it three days
into Phase 1.

The other four phases land closer to the existing plan:

| Priority | This list's phase | Nominal ROADMAP/RFP phase | Existing spec |
|---|---|---|---|
| 1 | Chat backend + file/voice storage | Not in Phase 1–3; RFP's lowest tier | none — new, §1 below |
| 2 | Survey backend + PDF/Excel | Phase 3, "Surveys and questionnaires" | none — new, §2 below |
| 3 | Attendance daily record + reports | Phase 3, "attendance" — but most of the backend already exists | `2026-08-18-attendance-meal-finance-frontend.md` §2–3 |
| 4 | Assessment → dashboard charts | Phase 2, "improved dashboards" | `2026-08-18-progress-overview-backend.md` (group-level detail); §4 below covers the admin/parent-360 gap it doesn't |
| 5 | Meal + finance module | Phase 3 ("attendance," QPay) + `нэмэлт.md`/`FINANCE_SCOPE.md` | `2026-08-18-attendance-meal-finance-frontend.md` §4–5 |

---

## 1. Chat backend + file/voice storage

**Frontend today:** `templates/comms/list.html`'s `.chat-workspace` section
(`data-api="/api/v1/messages/"`, currently unfulfilled) — two tabs, two
thread lists, a compose form with attach/voice/text, and a local-only
message echo. Fully interactive, zero persistence, zero real-time. Read the
comment at that section's `{% if is_staff %}` block before starting — it's
there because a guardian's HTML must never *contain* the staff thread, not
merely hide it with CSS.

### 1.1 Data model

Nothing under `apps/comms/` models this today — `Announcement` is one-way
broadcast (a post, with readers), not a conversation. Suggest a new
`apps/messaging/` app rather than folding this into `comms`:

```
Thread             TenantScopedModel
    kind             TextChoices: "family" (parent<->teacher, scoped to a
                      child or group), "staff" (teacher-internal, no
                      guardian can ever be a participant)
    child            FK -> Child, null=True
    group            FK -> Group, null=True

ThreadParticipant  TenantScopedModel  (or a plain M2M through-table)
    thread           FK -> Thread
    user             FK -> User

Message            TenantScopedModel
    thread           FK -> Thread
    author           FK -> User
    body             TextField, blank=True
    attachment       FK -> MediaFile, null=True
    voice_note       FK -> MediaFile, null=True
```

Reuse the existing `MediaFile` + signed-URL pipeline for both attachment
types (CLAUDE.md §1.4/§1.6) — do not invent a second file path or a public
bucket. `python-magic` MIME sniffing decides image vs. video vs. audio; the
frontend's `accept="image/*,video/*"` on the file input and separate voice
button are UI affordances only, not something the backend should trust for
type dispatch.

**Authorization:** a `can_access_thread(user, thread)` predicate in
`apps/core/permissions.py`, same shape and same file as `can_access_child` —
404, never 403. A `kind="staff"` thread must be unreachable for any
non-staff role *at the permission-function level*. The frontend enforces
isolation by never emitting the markup at all for a guardian; the backend
needs to match that strength independently — a guardian who guesses a
staff-thread URL is exactly the RFP §21.4 scenario ("changing the URL must
not reveal another child's — or here, another conversation's — data").

### 1.2 The exact frontend contract to satisfy

- Tabs: `data-chat-tab="parents"` / `="teachers"` — the second tab's button
  and its entire sidebar (`data-chat-sidebar="teachers"`) only exist in the
  DOM when the view passes `is_staff` true. Nothing to build here except
  making sure the real thread list behind each tab matches: a group thread
  ("Бүх эцэг эх" / "Бүх багш нар") plus a 1:1 picker ("Хүүхэд сонгох" /
  "Удирдлага руу бичих").
- Compose form (`data-chat-send`): `message` text input, `attachment` file
  input, and a voice-record toggle (`data-chat-voice`) that today only runs
  a local timer — no `MediaRecorder` capture exists yet. Wiring actual audio
  capture/upload is part of this phase, not a stub to discover missing.
- `data-chat-messages` currently only appends the sender's own just-sent
  text locally (`chat-workspace__bubble--mine`) as a stand-in for a real
  thread. Replacing that local echo with a GET-on-load history plus
  server-confirmed sends is the actual deliverable.

### 1.3 Real-time transport

"Шууд харилцах" (client's wording) — Django Channels/WebSocket is the
natural fit; a short-poll fallback is acceptable to the frontend too, since
nothing there assumes a specific transport, only that new messages land in
`data-chat-messages`. Whichever is chosen, say so explicitly — Channels
changes the deployment shape (`ROADMAP.md` §15 doesn't currently provision
an ASGI server or a channel layer), and that's infrastructure, not code.

### 1.4 Testing

CLAUDE.md §4.1's three mandatory tests, plus a fourth specific to this
phase: a guardian who requests a staff thread's id directly must 404, not
merely fail to see a link to it.

---

## 2. Survey backend + PDF/Excel

**Frontend today:** a complete, working survey **builder and list** against
`localStorage` (`templates/dashboard/teacher.html`, key `teacher-surveys-v1`
— search that string) as an explicit stand-in for the real backend. This
was built to the shape a real API would need, specifically so swapping
`localStorage.getItem/setItem` for `fetch()` calls is close to a drop-in
replacement rather than a redesign.

### 2.1 The localStorage schema — replicate this shape server-side

```js
{
  id: "sv<timestamp>",
  createdAt: "<ISO 8601>",
  title: "<string>",
  type: "poll" | "form",
  closesOn: "<YYYY-MM-DD>" | "",
  questions: [
    { text: "<string>", answerType: "choice" | "check" | "text",
      options: ["<string>", ...] }
  ]
}
```

A `poll` always has exactly one question; a `form` has one or more — the
frontend's own type switch already enforces that client-side, so the
backend doesn't need to re-derive it, only accept it.

### 2.2 Data model

```
Survey            TenantScopedModel
    title
    kind            TextChoices: poll, form
    closes_on       DateField, null=True
    target_group    FK -> Group, null=True   # null = whole kindergarten
    status          TextChoices: draft, published, closed

SurveyQuestion    TenantScopedModel (or a plain FK — no independent
                   soft-delete story needed for a question that only ever
                   exists inside one survey; check how this project handles
                   other parent/child pairs like AnnouncementTarget before
                   deciding)
    survey          FK -> Survey
    order           PositiveSmallIntegerField
    text
    answer_type     TextChoices: choice, check, text
    options         JSONField, or a separate SurveyOption table. A
                     JSONField is defensible here despite CLAUDE.md §2.3:
                     that rule is about admin-editable *shared*
                     configuration (DevelopmentDomain, AssessmentLevel) —
                     one survey's own answer options belong to that survey
                     alone and are never reused elsewhere.

SurveyResponse    TenantScopedModel
    survey          FK -> Survey
    guardian        FK -> User
    child           FK -> Child     # the client's flow is per-child, not
                                     # per-guardian-account — a guardian of
                                     # two children in the same class answers
                                     # once per child
    submitted_at

SurveyAnswer
    response        FK -> SurveyResponse
    question        FK -> SurveyQuestion
    value           TextField, or JSONField for a multi-select "check" answer
```

### 2.3 Services/selectors the frontend is waiting for

- Create/update/publish/delete a survey. Publishing is where the client's
  flow says **"шууд ангийн самбарт постлогдоно"** — decide whether that
  means a Survey creates a companion `Announcement`, or the classboard feed
  learns to read `Survey` rows directly. `templates/comms/list.html`'s
  classboard doesn't know surveys exist yet either way; pick one and update
  that template's query.
- Guardian-facing: list open surveys targeted at their child's group,
  submit a response. `templates/children/parent/detail.html`'s
  `#parent-surveys` section and `static/css/parent-survey.css` are the
  existing frontend target for this.
- Teacher-facing results: who answered / who hasn't, per-question
  breakdown. `.teacher-surveys__result-grid` and `.teacher-surveys__bars`
  in `dashboard/teacher.html` are built and waiting on real numbers —
  currently rendered as an explicit zero/em-dash state.
- PDF/Excel export — **Celery, not inline** (CLAUDE.md §6), tracked through
  the existing `ReportJob` pattern already used for the child portfolio PDF
  (`apps/reports/`) rather than a second job-tracking table. Every
  "PDF татах"/"Excel татах" button in the shipped UI already shows the
  loading spinner and an honest "Backend холбогдоход ... шууд татагдана."
  toast (`static/js/ui-states.js` — see the "UI STATES" section of
  `app.css`) — only the endpoint itself is missing.

### 2.4 Migration note

Once real, the frontend's `localStorage`-backed survey list becomes dead
code to delete, not dead code to keep working alongside the API —
`renderTeacherSurveys()` in `dashboard/teacher.html` is the single function
that would need to switch from `loadSurveys()`/`saveSurveys()` to `fetch()`
calls; nothing else in that file needs to change shape.

---

## 3. Attendance daily record + reports

Most of this phase's backend already exists and is already tested — read
`2026-08-18-attendance-meal-finance-frontend.md` §2–3 in full before
starting here; it maps exactly this client flow onto the codebase and this
section only adds what that document doesn't cover.

### 3.1 Already done — do not rebuild

- `Attendance` model (`apps/attendance/models.py`): six-state closed
  vocabulary (`present`/`excused`/`sick`/`absent`/`half_day`/`other`), one
  row per `(enrollment, date)`, `simple_history` on every row.
- `apps/attendance/services.py`: `record_attendance`, `record_group_day` —
  **both already call `audit()` in the same transaction as the write**
  (CLAUDE.md §3.3's "Common mistakes" row is already satisfied here, not a
  gap).
- `apps/attendance/selectors.py`: `group_day_sheet`, `child_attendance`,
  `monthly_status_counts`, `unmarked_children` — everything the three
  screens below need already exists as a function call, not a query to
  write from scratch.
- The accountant-role routing fix (seed user, `layout_for`, post-login
  redirect) described in that spec's §2 — still needed, still small, still
  blocking every screen below it if skipped.

### 3.2 Missing: views/urls/templates layer

No `apps/attendance/views.py` exists at all — this is a thin layer over
already-tested services, exactly the CLAUDE.md §2.1 shape (parse request,
call service, return response):

- **Багшийн "Өнөөдрийн ирц"** — replaces the mock-up panel already in
  `dashboard/teacher.html` (its own comment says *"Энэ нь frontend бэлтгэл
  дэлгэц"*). One page per group per day, backed by `group_day_sheet` +
  `record_group_day`. The status buttons/colors already in that template
  were built to match `AttendanceStatus`'s six values, so no redesign
  needed there.
- **Удирдлагын "Ирцийн нэгтгэл"** — `templates/dashboard/admin.html` now has
  a real panel (`.admin-attendance-bars`, three group rows, added
  2026-08-18) sitting on an honest zero-data placeholder, waiting on
  `monthly_status_counts(group=…, year, month)` per group. That selector
  already returns **counts per status**, never a single collapsed number —
  keep it that way in the view/template; collapsing "present + half_day"
  into one funding figure is a policy decision (`FINANCE_SCOPE.md` D4)
  that hasn't been made yet.

### 3.3 New since that spec was written: guardian-submitted leave/sick requests

`templates/children/parent/detail.html`'s `#parent-attendance` section
(built 2026-08-18, after the spec above) has two real, interactive forms
with no backend counterpart yet:

- **"Чөлөө хүсэх"** — date range (`leave_from`/`leave_to`) + free-text
  reason (`leave_reason`).
- **"Өвчний акт хавсаргах"** — a file (`accept="image/*,application/pdf"`,
  route through the existing `MediaFile` pipeline, not a new upload path)
  plus notes.

Neither maps onto an existing model. This needs something like a
`LeaveRequest` (or extend `Attendance` with a `source` field distinguishing
a teacher's own mark from a guardian's submitted request pending review) —
a guardian's submission should not silently become the day's `Attendance`
row; a teacher reviewing and confirming it is what the client's flow
describes ("Багш: ... баталгаажуулна"). Whichever shape is chosen, it needs
the same `audit()`-in-transaction pattern §3.1 already follows.

### 3.4 Testing

The three CLAUDE.md §4.1 tests on every new view. `Attendance`'s own
`simple_history` plus the existing `audit()` calls already satisfy "who
changed what" for corrections — no new audit work needed there, only for
the new leave-request flow in §3.3.

---

## 4. Assessment → dashboard charts

Two different audiences need two different things here, and only one of
them has a written spec already.

### 4.1 Already spec'd: the teacher's group-level view

`2026-08-18-progress-overview-backend.md` covers `group_grid.html`'s
month/quarter/year progress tabs, the `ObservationNorm` model, the
`monthly_progress`/`quarterly_progress`/`yearly_progress`/
`recommended_children` selectors, and the "Санал болгох хүүхэд" panel in
full — read that document, not this section, for that piece. Nothing here
duplicates it.

### 4.2 Already real, no backend needed

- `templates/assessment/child.html`'s "Хөгжлийн тайлан" report dashboard
  (the `?report=1` view, also the default for a guardian/admin visiting the
  page): the per-domain quarterly bar chart and the "▲ Ахиц / ▼ Буурсан /
  Тогтвортой" trend badge are both computed entirely from `matrix` — the
  data `assessment:child_assessment` already assembles. No new
  selector needed for this piece.
- `dashboard/teacher.html`'s "Хөгжлийн ахицын нэгдсэн график" — backed by
  `apps.dashboard.selectors._domain_averages`, already real, already wired,
  already shipped. Confirmed by reading the selector directly — this is not
  a gap.

### 4.3 The actual gap: admin-wide aggregation and a monthly figure

`apps.dashboard.selectors.compute_admin_dashboard` (the function behind
`dashboard/admin.html`) returns **raw counts only** — kindergartens,
groups, teachers, children, observations, assessments, announcements,
enrollments, storage, reports, failed logins. No per-domain average, no
per-group breakdown, nothing assessment-shaped. Three panels in
`dashboard/admin.html` are honest zero-data placeholders waiting on this:

- **"Бүлгүүдийн явцын үнэлгээ"** (`.admin-radar-placeholder`) — a per-domain
  average across every group the administrator can see, same shape as
  `_domain_averages` but aggregated across groups instead of one group's
  children.
- **"Бүлгүүдийн судалгааны харьцуулалт"** — depends on Phase 2 existing
  first (survey participation per group).
- **"Багш нарын гүйцэтгэл"** (`.admin-lines`) — observation/assessment/
  survey volume per teacher. No existing selector groups any of these by
  author/teacher today; check `_recent_observations`/`_recent_parent_notes`
  in `apps/dashboard/selectors.py` for the closest existing pattern before
  writing a new one.

None of the three above have a written model/selector spec yet — this
document is flagging the gap, not resolving it; whoever picks this up
should treat `_domain_averages`'s existing shape (kindergarten-scoped
instead of group-scoped, same aggregation) as the template to extend rather
than a fresh design.

### 4.4 The other actual gap: "сар" (monthly), not just "улирал" (quarterly)

`templates/assessment/child.html` has an honest, explicitly-empty "Сарын
идэвхийн ахиц" panel (added 2026-08-19) because assessments are recorded
per `Term`, not per calendar month — there is no monthly bucket to show a
real number for today. Two different things could satisfy "сар...ахиц":

1. A literal monthly assessment cadence (assessing more often than once a
   term) — a scope decision, not just a query.
2. Monthly **observation activity** (how often a child was actually
   observed/noted each month) — this has a real per-row date already
   (`Observation.observed_on`) and only needs a `TruncMonth` aggregation, no
   new model. This is very likely what the client means and is the cheaper,
   more honest thing to build — decide and confirm before assuming the
   harder one.

Whichever is chosen, `assessment:child_assessment`'s view (`apps/assessment/
views.py`) is where the new context key belongs, next to the existing
`matrix`/`terms`.

---

## 5. Meal + finance module

Read `2026-08-18-attendance-meal-finance-frontend.md` §4–5 in full — it
already maps the client's exact flow ("Багш: Ирц + хоол бүртгэнэ → Систем
нэгтгэнэ → Удирдлага/нягтлан тооцно → Эцэг эх төлнө") onto what exists
versus what's missing, and this section only adds what's changed since.

### 5.1 Summary of that document's findings (still accurate)

- **Meal register:** no `MealRecord` model exists. `нэмэлт.md` §2 wants the
  same shape as `Attendance` (per child, per day, teacher-recorded,
  `simple_history`) — build it as a sibling of `Attendance`, not a
  variant of it, since a meal day and an attendance day are recorded
  independently even though they usually coincide.
- **Funding/tariff/invoice/payment:** nothing exists, not even a stub
  beyond a docstring example. `FINANCE_SCOPE.md` §7's open decisions
  (D1–D8 — the funding formula itself, what counts as a funding day, the
  reversal-entry model for corrections) must be resolved before any of this
  is built on real numbers rather than a guessed formula. That document's
  own words: building on a guess "produces confident wrong numbers."
- **Accountant role:** permission predicates exist and are tested
  (`can_view_finance`, `can_manage_finance`, `can_view_child_finance` in
  `apps/core/permissions.py`), but the role has no landing page — see
  §2 of the linked spec for the three small routing fixes needed before
  any finance screen is reachable at all.

### 5.2 QPay / SocialPay

Not analyzed in the linked spec — this is genuinely new scope, ROADMAP
Phase 3's "tuition invoices, QPay/SocialPay" line. Needs its own
integration spec (webhook handling, payment-state reconciliation, what
happens to an `Invoice` when a webhook never arrives) before implementation
starts; out of scope for this document to design blind.

### 5.3 Frontend waiting for this phase

`dashboard/admin.html`'s `.kitchen-ready` section (recipe/menu/stock/
hygiene tabs) and `.finance-ready` grid, plus
`templates/children/parent/detail.html`'s `#parent-meals`/`#parent-finance`
sections — all explicit, honest zero-data prep screens, all already styled
and interactive, all waiting on the model layer this section describes.

---

## 6. What "done" looks like for each phase

Per CLAUDE.md §4.1, no phase above is done without the three mandatory
cross-tenant/cross-role tests **through the HTTP client** on every new view
touching child data — a passing `apps/core/tests/test_permissions.py` proves
the predicate works, not that the view calls it. And per CLAUDE.md §7.3: if
a test fails, say so; if a step gets skipped, say so; when something is
actually done, say so plainly, without hedging.

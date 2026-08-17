# Scope assessment — `нэмэлт.md` (attendance, meals, funding, billing)

**Source:** `/Users/usukhbayar/Downloads/нэмэлт.md`, 17 sections.
**Assessed:** 2026-08-17. **Status: assessed, not built.**

No feature code was written. CLAUDE.md §7.1 requires that work belonging to a
later phase is named as such and pulled forward deliberately, not on the
assistant's initiative. This document is that step. §9 lists what is needed to
start.

---

## 1. The headline

This is not an addition to the portfolio system. It changes what the product
**is**.

Today the system records what a child did and how they are developing. If
a record is wrong, a teacher edits it and the harm is a wrong sentence in a
portfolio. Everything in `нэмэлт.md` is downstream of one new fact — *was
this child here today* — and that fact becomes money: meal cost, state
funding claims, parent invoices, payments.

**A wrong attendance mark becomes a wrong funding claim to the government.**
That is a different category of defect from a wrong observation, and it is
why this cannot be treated as "a few more screens".

Product category before → after:

```
  Child development portfolio        Kindergarten operations + finance system
  ───────────────────────────        ────────────────────────────────────────
  observations, assessments     →    attendance, meals, state funding,
  photos, PDF portfolio              invoices, payments, reconciliation,
                                     accountant role, financial audit
```

## 2. Phase placement — all 17 items

Ranked by where the existing agreed documents put them.

| § | Item | Where it belongs today | Evidence |
|---|---|---|---|
| 1 | Attendance register | **Phase 3** | ROADMAP §9 "attendance"; RFP appendix §949 |
| 2 | Meal register | **Phase 3 (partial) / NEW** | RFP §989 covers the *menu*, not per-child meal-taken records |
| 3 | Meal cost accounting | **NEW — not in the RFP** | no tariff or cost concept anywhere in the RFP |
| 4 | State funding module | **NEW — not in the RFP** | see §3 below |
| 5 | Funding rules engine | **NEW — not in the RFP** | see §3 below |
| 6 | Monthly funding calculation | **NEW — not in the RFP** | see §3 below |
| 7 | Parent payments / invoices | **Phase 3** | ROADMAP §9 "tuition invoices"; RFP §976 |
| 8 | Online payment (QPay, SocialPay) | **Phase 3** | ROADMAP §9; RFP §976 |
| 9 | Financial dashboard | **NEW** | depends on 3–8 |
| 10 | Finance tab on the child profile | **NEW** | depends on 3–8 |
| 11 | Allergy vs menu alerts | **Phase 3** | RFP §952, §989–990 |
| 12 | Daily and weekly menu | **Phase 3** | RFP §989 |
| 13 | Accountant role | **NEW** | RFP §56 defines four roles; accountant is not one |
| 14 | Financial audit log | **Extends Phase 1** | `AuditLog` exists; before/after values do not |
| 15 | Import from existing systems | **NEW** | RFP §19 mentions government integration as "future" |
| 16 | Financial reports (9 of them) | **NEW** | none of the nine is in RFP §10.2 |
| 17 | Single-entry principle | **Architecture rule** | not a feature; constrains all of the above |

**Nothing in this document is Phase 1 or Phase 2.** Phase 1 is finished but
uncommitted and undeployed, with four open blockers in
`docs/PRODUCTION_READINESS.md` §9.

## 3. The state funding module is new contract scope

This is the largest and most consequential claim in this document, so it is
evidenced rather than asserted. Word counts across the **entire** RFP
(`Project_Info.md`):

| Term | Occurrences in the RFP |
|---|---|
| санхүүжилт (funding) | **0** |
| тариф (tariff) | **0** |
| нягтлан (accountant) | **0** |
| хөнгөлөлт (discount) | **0** |
| invoice | **0** |
| төлбөр (payment) | 5 — all in the Phase 3 appendix |
| ирц (attendance) | 3 — all in the Phase 3 appendix |

Sections 3, 4, 5, 6, 9, 10, 15 and 16 of `нэмэлт.md` — the whole funding and
financial-reporting half — have **no basis in the RFP at all**. They are not
deferred work being pulled forward; they are new scope.

This matters commercially, not just technically: the RFP is the agreed
definition of the deliverable, and §21's acceptance criteria are written
against it. Adding a state-funding subsystem is a change of contract, and
should be priced and scheduled as one.

## 4. Where this collides with existing architecture

Six real problems. Each has a decision attached; none is a blocker forever,
but each is much cheaper to settle before code than after.

### 4.1 Attendance must hang off `Enrollment`, not `Child`

`Enrollment` already carries `child`, `group`, `school_year`, `started_on`,
`ended_on`. A child who transfers mid-year has two enrollments, and their
attendance in March belongs to whichever kindergarten they attended in
March.

Attaching attendance to `Child` would attribute the whole year to the
current kindergarten — and since funding is *calculated from attendance*,
that is a funding claim by the wrong institution. This is the same rule as
CLAUDE.md §1.2, now with money attached.

### 4.2 Money must not be a float

Every amount — tariff, calculated, confirmed, received, difference, invoice
total — must be `DecimalField`. A `FloatField` gives 0.1 + 0.2 ≠ 0.3, and a
reconciliation report (§6, §16) whose columns fail to sum by one tögrög is
worse than useless: it destroys trust in every other figure on the page.

### 4.3 A calculation must freeze the tariff it used

§5 makes tariffs time-bounded (`valid from`, `valid to`). If a monthly
calculation stores only *a reference* to the rule, then editing a tariff
later silently rewrites what was claimed and approved months ago.

Every calculated row must store the **numbers it was computed from** — the
tariff, the day count, the rule version — not just a foreign key. Otherwise
the `Draft → Submitted → Approved → Paid → Reconciled` chain in §6 cannot be
audited, because no one can reproduce what "Approved" approved.

### 4.4 `AuditLog` cannot express before → after today

§14 requires `Хэн → Хэзээ → Юу → Өмнөх утга → Шинэ утга`.

The existing `AuditLog` has `actor_user`, `action`, `object_type`,
`object_id`, `ip_address` and a `metadata` JSON field — but **no structured
old-value / new-value columns**. `metadata` could carry them as loose JSON,
but then the financial audit report in §16 cannot query or reconcile them.

`simple_history` is already installed and used on `Child` and two portfolio
models; it records full row versions and is the more likely fit here.
**Decision needed:** structured columns on `AuditLog`, `simple_history` on
the financial models, or both.

### 4.5 §3.3 "no hard deletes" is necessary but not sufficient

CLAUDE.md §3.3 uses soft delete: set `deleted_at`, hide from the manager.
That is right for an observation. It is **wrong for a confirmed payment** —
`нэмэлт.md` §14 says so itself: *"Баталгаажсан санхүүгийн гүйлгээг шууд
устгахгүй. Залруулга эсвэл reversal transaction ашиглана."*

A soft-deleted payment vanishes from every report while its money stays in
the totals. Financial records need a **reversal entry** — a new, opposite row
that leaves both the error and the correction visible. This is a stricter
rule than §3.3, not a variation of it, and CLAUDE.md will need a section
saying so.

### 4.6 The accountant role is a new authorization axis

`Role` today is `SUPERADMIN / ADMIN / TEACHER / GUARDIAN`, and every access
question is "may this person see **this child**". `apps/core/permissions.py`
is built entirely around that question.

An accountant asks a different one: they need every invoice in the
kindergarten but no developmental observations, and §13 says teachers must
*not* see full financial data. That is a second dimension — *which kind of
data*, not *which child* — and it lands in the file CLAUDE.md §1.1 calls
"the most important 30 lines in the system".

This is doable and normal. It is called out because a mistake here is a
privacy breach in the file that currently has the strongest guarantees, and
because retro-fitting a second axis is far harder than designing for it.

## 5. Build order

The dependency chain is close to linear, which is good news for planning and
bad news for parallelising. Nothing downstream can be trusted until
attendance is right.

```
        ┌─────────────────────────┐
        │  §1  ATTENDANCE         │  ← the single source of truth (§17)
        └───────────┬─────────────┘
                    │
        ┌───────────┴─────────────┐
        │                         │
   ┌────▼────┐              ┌─────▼──────┐
   │ §2 meal │              │ §5 funding │
   │ register│              │   rules    │
   └────┬────┘              └─────┬──────┘
        │                         │
   ┌────▼────┐              ┌─────▼──────┐
   │ §3 meal │              │ §4,6 state │
   │  cost   │              │  funding   │
   └────┬────┘              └─────┬──────┘
        └───────────┬─────────────┘
                    │
        ┌───────────▼─────────────┐
        │  §7 invoices            │
        └───────────┬─────────────┘
                    │
        ┌───────────▼─────────────┐
        │  §8 online payment      │
        └───────────┬─────────────┘
                    │
     ┌──────────────┼──────────────┐
┌────▼────┐   ┌─────▼─────┐  ┌─────▼─────┐
│ §9 dash │   │ §10 child │  │ §16 nine  │
│ board   │   │ finance   │  │  reports  │
└─────────┘   └───────────┘  └───────────┘

Cross-cutting, must be designed BEFORE the chain, not bolted on after:
  §13 accountant role  ·  §14 financial audit  ·  §17 single-entry principle

Independent of the money chain, can run in parallel:
  §11 allergy alerts  ·  §12 menu        (both are child-safety, not finance)
```

Two notes on the diagram:

- **§11 and §12 are the cheapest real value here.** Allergy-vs-menu checking
  is child safety, needs no money, no accountant and no reconciliation, and
  the allergy data partly exists already (`Child.health_notes`). If something
  must ship soon, this is the candidate.
- **§8 online payment should be last.** It is the only item that touches an
  external party's money, and it is worthless until invoices (§7) are
  correct.

## 6. Honest size

Phase 1 — the portfolio system as it stands — is 958 tests over roughly ten
working days of scoped effort.

`нэмэлт.md` is 17 modules, of which 8 are new subsystems rather than screens.
It includes a rules engine (§5), a state machine with five states (§6), an
external payment integration (§8), a data-import path (§15) and nine reports
(§16). **It is larger than everything built so far**, and its correctness bar
is higher because the output is money and a government claim.

No day estimate is offered here, because an estimate produced before the
decisions in §7 are answered would be fiction.

## 7. Decisions needed before any code

Ordered so the cheap ones do not wait on the expensive ones.

| # | Decision | Why it blocks |
|---|---|---|
| D1 | Is this new scope, contractually? | §3 shows the funding half is absent from the RFP. Affects price and timeline, not just the plan. |
| D2 | Does Phase 1 ship first? | Phase 1 is complete but uncommitted, with four open blockers. Starting here leaves finished, tested work undelivered. |
| D3 | Which funding rules actually apply? | §5 is a rules *engine* with no rules in it. The real government formula, its age bands and its attendance definition are needed — a guessed formula produces confident wrong numbers. |
| D4 | What counts as an attendance day for funding? | Does "Хагас өдөр" count as a full day? Does "Чөлөөтэй" count? Every downstream figure depends on this one answer. |
| D5 | Audit approach (§4.4) | Structured columns, `simple_history`, or both. |
| D6 | Reversal model (§4.5) | Confirms the stricter-than-§3.3 rule before financial models exist. |
| D7 | Accountant permission boundary (§4.6) | Exactly what an accountant may see, and what a teacher may not. |
| D8 | Which existing system is being imported from (§15) | Determines whether §15 is an afternoon of CSV work or a month of API integration. |

D3 and D4 are the two that cannot be worked around. Everything from §3 to
§16 computes a number, and without the real rules those numbers would be
plausible, precise and wrong — the worst possible failure mode for a claim
submitted to a government body.

## 8. Recommendation

Three options, in the order I would rank them.

**A. Finish Phase 1, then start this as a costed Phase 4.** Phase 1 is done
and tested; it should be committed, deployed and signed off rather than
abandoned one step from delivery. Meanwhile D1–D8 get answered properly.

**B. Ship §11 + §12 now (allergy alerts and menu), defer the money.** These
two are child-safety, need none of the financial machinery, and are the only
items here that could be added without answering D3 and D4. Real value, small
surface.

**C. Start the finance chain now.** Only sensible if D1, D3 and D4 already
have real answers. Beginning at §1 attendance without them means building the
foundation of a calculation whose rules are still unknown.

## 9. Build log

**2026-08-17 — the client instructed: build all of it.** D3 and D4 (the real
funding formula, and what counts as a funding day) are still unanswered.

That turned out not to block the build, for a reason the requirement itself
supplies. `нэмэлт.md` §4 says:

> Санхүүжилтийн тариф болон дүрмийг source code-д тогтмол бичихгүй.
> Администратор тохиргоогоор өөрчлөх боломжтой байна.

The tariffs and rules are *required* to be configuration, not code. So the
engine is being built with the rule table empty, and the unknown formula is
entered by an administrator rather than guessed by a developer. **No number
from a government schedule is hard-coded anywhere.**

D4 is handled the same way: `monthly_status_counts` reports days *per
status* and never collapses them into a single "funding days" figure. What a
half day is worth becomes a weight in the funding rule. A test
(`test_monthly_counts_carry_no_funding_policy`) fails if anyone later folds
that decision back into the query.

### Tranche 1 — foundation ✅ complete

| Item | What was built |
|---|---|
| §13 accountant role | `Role.ACCOUNTANT`; a **separate** finance permission axis in `apps/core/permissions.py` — `finance_kindergartens`, `can_view_finance`, `can_manage_finance`, `can_view_child_finance` |
| §1 attendance | `apps/attendance/` — model, services, selectors, 18 tests |
| §14 audit (start) | corrections carry `previous_status` → `new_status`; `simple_history` on the row |

**989 tests pass** (was 958), ruff clean, `makemigrations --check` clean.

The separation in §4.6 is guarded in both directions and verified by
deliberately breaking it: adding `ACCOUNTANT` to `can_access_child` fails
`test_an_accountant_cannot_see_a_childs_developmental_record` **and** the
list/detail equivalence invariant in `test_permissions.py`, which now
includes an accountant among its users.

### Remaining

§2 meal register · §3 meal cost · §4–6 funding rules, state funding, monthly
calculation · §7 invoices · §8 online payment · §9 financial dashboard ·
§10 child finance tab · §11 allergy alerts · §12 menu · §15 import/export ·
§16 the nine reports · plus the §14 reversal rule for confirmed transactions.

### Still needed from the client

D3 and D4 remain open. They no longer block **construction**, but they block
**use**: the funding engine will run with an empty rule table, and until a
real rule is entered it will correctly calculate nothing. The tariffs, age
bands and the definition of a funding day still have to come from the
government schedule.

# UI/UX design reference

Client-supplied mockups in `screens/`. Renamed from their original
`photo_2026-08-08 20.07.NN.jpeg` filenames by reading the Mongolian screen
title inside each image.

These are the designs RFP §21.15 measures the build against ("the system must
match the design and user flows the client approved"), and §19 lists them as a
handover item. Treat them as the reference for layout and copy, not as a scope
decision — see "Scope" below.

Naming: `<role>-<screen>.jpeg`. Sheets showing several screens at once are
prefixed `overview-`.

---

## Authentication

| File | Screen title in image | Notes |
|---|---|---|
| `auth-login-and-password-reset.jpeg` | Нэвтрэх болон нууц үг сэргээх урсгал (Web) | Full flow: login → **6-digit OTP** → new password → success. Role tabs (Багш / Эцэг эх / Админ). States the lockout rule: 5 failures → 15 minutes |

## Teacher

| File | Screen title in image | Notes |
|---|---|---|
| `teacher-dashboard.jpeg` | Багшийн хяналтын самбар | Six KPI tiles, own group's children, recent observations, domain averages, attendance, parent messages, health flags, growth, survey progress, weekly plan |
| `teacher-dashboard-alt.jpeg` | Хяналтын самбар | Variant with a grouped sidebar (Миний хэсэг / Хувийн хавтас / Ажиглалт & Үнэлгээ / Харилцаа). Adds payments and a Quick-statistics panel |
| `teacher-children-list.jpeg` | Хүүхдийн жагсаалт | Table with photo, code, name, sex, DOB, age, enrolment date, status, guardians. Filters: group, status, sex, age. Excel import/export. Pagination |
| `teacher-child-profile-360.jpeg` | Хүүхдийн 360° хавтас | Tabbed profile: 360° тойм, Миний тухай, Portfolio (2–5 нас), Ажиглалт, Үнэлгээ, Эрүүл мэнд, Ирц, Хоол, Харилцаа, Баримт, Санхүү. Radar chart, milestone timeline, album, guardians |
| `teacher-observation-form.jpeg` | Ажиглалтын маягт – Шинэ ажиглалт оруулах | Six-section form. Includes a voice note with speech-to-text, tags, teacher-confidence star rating, and a completeness checklist |
| `teacher-observation-form-alt.jpeg` | Шинэ ажиглалт бүртгэх | Denser variant of the same form, with a live radar chart |
| `teacher-assessment-matrix.jpeg` | Түргэн үнэлгээ (Matrix) | Whole group × nine domains, one click per cell, four colour-coded levels, side panel with the selected child's detail. Matches RFP §6.3 |
| `teacher-report-builder-pdf.jpeg` | Тайлан үүсгэгч & PDF харах | Report type → child → term → section checkboxes → settings (language, A4, template, watermark) with a live PDF preview and page thumbnails. Matches RFP §10.1 |
| `teacher-feed-and-messages.jpeg` | Харилцаа / Өдөр тутмын мэдээ | Announcement + post feed with photos, likes, comments, read counts; today's summary; parent message list |
| `teacher-attendance-health.jpeg` | Ирц, Эрүүл мэнд | Daily attendance table, temperature and wellbeing entry, red-flag panel |
| `teacher-surveys-analytics.jpeg` | Судалгаа & Аналитик | Survey list, response rates, analytics, start-vs-end comparison |

## Parent / guardian

| File | Screen title in image | Notes |
|---|---|---|
| `parent-home.jpeg` | Нүүр хуудас | Child switcher in the header (RFP §2.3), child card with links to the 360° page and portfolio, teacher feed with photos, upcoming events, per-domain progress bars, quick-link grid, support widget |

What the parent home needs from the MVP: the child switcher, child card,
teacher feed, announcements, domain progress, and the portfolio link. The rest
of its sidebar — Өнөөдрийн мэдээлэл, Ирц & Эрүүл мэнд, Хоол & Цэс, Мессеж,
Судалгаа, Төлбөр & Нэхэмжлэл — is deferred work.

**One conflict to resolve.** The design fixes a single kindergarten's name and
logo in the top-left, with only the child varying in the dropdown. Spec section
4.2 allows a guardian to have children at two kindergartens, and resolves the
tenant from the child rather than the session. So the branding and the
kindergarten label have to follow the **selected child**, not sit fixed in the
chrome. For a parent with children at one kindergarten — the common case —
the screen looks exactly as drawn.

## Administrator

| File | Screen title in image | Notes |
|---|---|---|
| `admin-dashboard.jpeg` | Администраторын хяналтын самбар | Counts for kindergartens / groups / teachers / children / guardians, growth chart, sex ratio, term assessment progress, storage usage, error and suspicious-activity counts |
| `admin-dashboard-alt.jpeg` | Администраторын хяналтын самбар | Variant. Adds user-activity chart, per-kindergarten usage table, domain averages, warnings list, system health |
| `admin-dashboard-alt2.jpeg` | Администраторын хяналтын самбар | Variant. Adds age distribution, recent audit-log entries, and a billing summary |
| `admin-dashboard-saas.jpeg` | Хяналтын самбар (Ирээдүй Өсөх) | Multi-tenant operator view: 128 kindergartens, 18,736 children, per-kindergarten status table, backup/restore panel, security alerts |

## Overview sheets

Several screens on one image. Useful for navigation structure and for the
parent-facing screens, which have no full-size mockup of their own.

| File | Contents |
|---|---|
| `overview-web-all-screens.jpeg` | Ten panels: login, teacher dashboard, child 360° profile, observation entry, assessment matrix, survey builder, health/attendance, communication, billing, report builder |
| `overview-login-and-dashboards.jpeg` | Login screens plus teacher, admin and **parent** dashboards |
| `overview-login-and-dashboards-alt.jpeg` | Same four, illustrated style. Parent panel shows Миний хүүхдүүд, growth chart, birthday, next payment |
| `overview-mobile-app-variants.jpeg` | Five visual styles for the mobile app, plus module screens and a proposed stack diagram |
| `overview-mobile-app-screens.jpeg` | Mobile app layout variants and per-feature screens |

## Duplicates

`screens/_duplicates/` holds three byte-identical copies and three
lower-resolution versions of images kept at full size. Safe to delete.

---

## Scope: what these designs imply

The mockups render the **whole RFP**, including everything spec section 1.2
defers. Every teacher screen's sidebar lists Ирц, Эрүүл мэнд, Судалгаа,
Хоол/цэс, Санхүү and Аюулгүй байдал, so building the navigation exactly as
drawn would promise all of it.

Outside the current MVP:

| In the design | Deferred to |
|---|---|
| Ирц, Эрүүл мэнд, Аюулгүй байдал, Эмийн санамж, Харшил | Module 2 |
| Судалгаа & Аналитик, Excel 5-sheet export | Module 1, §20-III |
| Санхүү, Төлбөр, QPay / SocialPay | Appendix (business) |
| Дуут тэмдэглэл, speech-to-text | Appendix |
| Хоол, цэс | Appendix |
| Авах/ирэх QR баталгаажуулалт | Appendix |
| Мессеж / чат | §20-IV |
| Mobile app | §20-IV |
| Хэл сонгох (MN switcher) | §20-IV |

**How to use this during the MVP:** build the layout, spacing, colour and copy
from these mockups, but render only the navigation entries that exist. Adding a
sidebar item later is trivial; a disabled or dead menu entry teaches users the
system is broken.

## Gaps and mismatches to resolve

| Item | Detail |
|---|---|
### Resolved

| Item | Decision |
|---|---|
| **Password reset method** | Keep the implementation's single-use hashed link, not the 6-digit OTP drawn in the design |
| **Password length** | Follow the design: 8+ characters, plus upper case, lower case and a digit (`PasswordComplexityValidator`) |
| **Role tabs on login** | Built as drawn, presentational only. They change which identifier the field asks for; authentication ignores them. Tests assert a teacher can log in with the "Эцэг эх" tab selected and that failure responses are identical across tabs |
| **Google / Apple sign-in** | Dropped. Not in the RFP |
| **Parent screens** | Supplied — see `parent-home.jpeg` |
| **Self-registration** | The design's "Бүртгүүлэх" link is not built. Staff create the account and the person activates it — see below |
| **Assistant teacher** | Already covered by `GroupTeacher.Role.ASSISTANT` |

### Still open

| Item | Detail |
|---|---|
| **Observation tags** | Design has "Холбогдох шошго (tag)". Not in the data model. Decide during the observation phase |
| **Teacher confidence rating** | Design has a 1–5 star "Багшийн итгэлцлийн түвшин" on observations. Not in the data model. Decide during the observation phase |
| **Child display code** | Design shows `CHD-0002` alongside the registration number. The model has one `national_id` field. Decide during the child-registration phase |
| **Storage quota per kindergarten** | Sidebars show "Хадгалах сан 12.6 GB / 50 GB". No quota field exists |

### Registration and activation

The design shows "Бүртгэлгүй юу? **Бүртгүүлэх**" on the login screen. Free
self-registration is not built, because it leaves one question unanswered:
how does the system know this person is that child's parent? The
`Guardianship` row *is* the §21.3 authorization boundary, so it cannot be
created by the person it grants access to.

Agreed flow:

- **Teacher** — the administrator creates the account (RFP §2.1) and the
  system issues an invitation. The teacher sets their own password.
- **Guardian** — the teacher registers the child and attaches the guardian,
  which creates the `Guardianship` immediately. The guardian receives an
  invitation and sets their own password.
- **Delivery** — an emailed single-use link where an address exists, and a
  six-digit code the teacher reads off the screen and writes on paper where
  it does not. Mongolian guardians frequently have no email, so the paper
  path is the primary one in practice. SMS arrives with §20-IV.

Staff never learn anyone's password.

## Confirmed by the designs

These validate decisions already made, which is worth recording:

- Assessment is **per development domain**, not per finer indicator — every radar chart and the matrix screen use the nine domains (spec section 6.4)
- Four colour-coded assessment levels, admin-configurable (RFP §6.2)
- Observations carry an "visible to parents" toggle (RFP §5.1)
- The lockout rule drawn on the login sheet — 5 failures, 15 minutes — matches `LOGIN_MAX_ATTEMPTS` and `LOGIN_LOCKOUT_MINUTES` exactly
- Milestone timeline, photo album, growth chart and PDF section picker all map to existing tables

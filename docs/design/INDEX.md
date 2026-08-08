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
| **No full-size parent screens** | The parent dashboard appears only as a small panel inside two overview sheets. Phase 3 builds exactly this. Worth requesting full-size mockups |
| **Password reset method** | Design uses a 6-digit OTP with a ~3-minute expiry; the implementation uses a single-use hashed link valid for 2 hours. Both satisfy RFP §3.1 — pick one |
| **Password length** | Design says 8+ characters; `AUTH_PASSWORD_VALIDATORS` is set to 10 |
| **Role tabs on login** | Design shows Багш / Эцэг эх / Админ tabs. The backend resolves role from `Membership`, so these can only be cosmetic — filtering authentication by the selected tab would turn the form into a role oracle |
| **Google / Apple sign-in** | Shown in one login variant. Not in the RFP; needs a decision |
| **Observation tags** | Design has "Холбогдох шошго (tag)". Not in the data model |
| **Teacher confidence rating** | Design has a 1–5 star "Багшийн итгэлцлийн түвшин" on observations. Not in the data model |
| **Child display code** | Design shows `CHD-0002` alongside the registration number. The model has one `national_id` field |
| **Storage quota per kindergarten** | Sidebars show "Хадгалах сан 12.6 GB / 50 GB". No quota field exists |
| **Assistant teacher** | Design shows Багш plus Туслах багш. Already covered by `GroupTeacher.Role.ASSISTANT` |

## Confirmed by the designs

These validate decisions already made, which is worth recording:

- Assessment is **per development domain**, not per finer indicator — every radar chart and the matrix screen use the nine domains (spec section 6.4)
- Four colour-coded assessment levels, admin-configurable (RFP §6.2)
- Observations carry an "visible to parents" toggle (RFP §5.1)
- The lockout rule drawn on the login sheet — 5 failures, 15 minutes — matches `LOGIN_MAX_ATTEMPTS` and `LOGIN_LOCKOUT_MINUTES` exactly
- Milestone timeline, photo album, growth chart and PDF section picker all map to existing tables

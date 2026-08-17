# Final device QA — Phase 1

**Status: NOT STARTED. No real device has been tested.**

Everything below is a plan to be executed by a person holding hardware. Nothing
in this file may be marked done from an emulator, a resized desktop window, or
Playwright. Those find layout faults; they do not find the faults this document
exists to catch — iOS Safari's zoom-on-focus, Android keyboard resize, real
camera upload, and the 100vh address-bar problem.

## What automated checking already covers

Stated narrowly, because a manual tester who believes a screen is covered will
skip it. **Only these routes were measured, and only at these widths:**

| Route | Widths | Result |
|---|---|---|
| `/` teacher dashboard | 375, 390, 768 | 0px overflow; no target < 44px; no control < 16px |
| `/` teacher dashboard | 1440 | 0px overflow |
| `/bagsh/huuhded/` children list | 375, 768, 1440 | 0px overflow; no target < 44px at 375/768 |
| `/bagsh/ajiglalt/hyanah/` review queue | 375, 768, 1440 | as above |
| `/medegdel/` announcements | 375, 768, 1440 | as above |

Teacher sidebar items measure 42px at 1440px only, where the input device is a
mouse; at 375 and 768 they are ≥44px.

**Not probed this session — assume nothing about them:** the observation form
(create and edit), the assessment group grid, teacher child detail, reports
request and status, comms detail, the profile screen, and every parent screen.
**1024px was not measured on any route.** These are the rows below that matter
most.

- **Authorization** — 958 tests, including HTTP-level 404 checks per CLAUDE.md §4.1.

**What no automated pass can cover, and why this document exists:** real touch
accuracy, real photo upload from a camera roll, real network latency, iOS
Safari's viewport and zoom-on-focus behaviour, Android's on-screen keyboard,
and whether Mongolian text renders in the fonts actually installed on a device.

## Devices

| # | Device | Browser | Owner | Status |
|---|---|---|---|---|
| D1 | iPhone (iOS 17+) | Safari | — | ☐ not started |
| D2 | Android phone | Chrome | — | ☐ not started |
| D3 | Desktop / laptop | Chrome | — | ☐ not started |
| D4 | Desktop / laptop | Safari | — | ☐ not started |

D1 and D2 are the priority: RFP §17 and CLAUDE.md §5 both put the phone first,
and parents will overwhelmingly use one.

## Parent flows

Run as a guardian account. Every screen must be legible one-handed.

| # | Flow | Pass condition | D1 | D2 | D3 | D4 |
|---|---|---|---|---|---|---|
| P1 | Log in with phone number | Numeric keyboard appears; no zoom on focus | ☐ | ☐ | ☐ | ☐ |
| P2 | Wrong password 3× | Attempts-remaining message is readable and correct | ☐ | ☐ | ☐ | ☐ |
| P3 | Request a password reset | Email arrives; link opens on the phone and resets | ☐ | ☐ | ☐ | ☐ |
| P4 | Home — child list | Cards tappable; no sideways scroll | ☐ | ☐ | ☐ | ☐ |
| P5 | Open the child profile | Photo not distorted; sections in order | ☐ | ☐ | ☐ | ☐ |
| P6 | Development summary | Level badges carry the level's own colour, not the domain's | ☐ | ☐ | ☐ | ☐ |
| P7 | Read an observation | Only observations marked visible appear | ☐ | ☐ | ☐ | ☐ |
| P8 | Submit a parent observation | Saves; appears as pending review | ☐ | ☐ | ☐ | ☐ |
| P9 | Attach a photo from the camera roll | Uploads; appears; HEIC handled or refused clearly | ☐ | ☐ | ☐ | ☐ |
| P10 | Open a photo | Loads through the signed URL, not a broken image | ☐ | ☐ | ☐ | ☐ |
| P11 | Announcements | Unread badge clears after reading | ☐ | ☐ | ☐ | ☐ |
| P12 | Request a PDF, then download it | Opens in the phone's PDF viewer; Cyrillic correct | ☐ | ☐ | ☐ | ☐ |
| P13 | Log out | Back button does not re-enter the session | ☐ | ☐ | ☐ | ☐ |

## Teacher flows

| # | Flow | Pass condition | D1 | D2 | D3 | D4 |
|---|---|---|---|---|---|---|
| T1 | Log in by username | Lands on the dashboard, correct group | ☐ | ☐ | ☐ | ☐ |
| T2 | Dashboard | Four tiles; each links somewhere real | ☐ | ☐ | ☐ | ☐ |
| T3 | Navigation | All six items reachable; the current one is marked | ☐ | ☐ | ☐ | ☐ |
| T4 | Children list — search | Mongolian text input works; results filter | ☐ | ☐ | ☐ | ☐ |
| T5 | Children list — filter and sort | Filters combine; paging keeps them | ☐ | ☐ | ☐ | ☐ |
| T6 | Open a child | Sections load; recent lists link onward | ☐ | ☐ | ☐ | ☐ |
| T7 | Record an observation | Every field reachable; the keyboard does not cover the save bar | ☐ | ☐ | ☐ | ☐ |
| T8 | Confirm the visibility default | **`visible_to_parents` is OFF** on a new observation | ☐ | ☐ | ☐ | ☐ |
| T9 | Attach a photo to a saved observation | Camera and gallery both work | ☐ | ☐ | ☐ | ☐ |
| T10 | Review a parent submission | Approve and reject both work | ☐ | ☐ | ☐ | ☐ |
| T11 | Assessment group grid | Sticky save bar never covers the last row | ☐ | ☐ | ☐ | ☐ |
| T12 | Assessment — save | Toast confirms; values persist after reload | ☐ | ☐ | ☐ | ☐ |
| T13 | Write an announcement | Targeting is correct; Mongolian input works | ☐ | ☐ | ☐ | ☐ |
| T14 | Generate a term report | Job status polls and completes without a manual refresh | ☐ | ☐ | ☐ | ☐ |
| T15 | Edit own profile | Saves; validation messages in Mongolian | ☐ | ☐ | ☐ | ☐ |

## Cross-cutting checks

Run these on **D1 and D2 at minimum** — they are where the automated pass is blind.

| # | Check | Why |
|---|---|---|
| X1 | No input zooms the page on focus | iOS Safari zooms under 16px and never zooms back |
| X2 | The on-screen keyboard never hides the field being typed into | Android resize behaviour |
| X3 | A sticky save bar never covers the last row of content | Verified at 375px in code; confirm on glass |
| X4 | Every Mongolian string renders — no boxes, no fallback serif | Device fonts differ from the container's |
| X5 | Rotate to landscape mid-form | Input must not be lost |
| X6 | Reload mid-form | Behaviour must be predictable |
| X7 | Slow network (throttle to 3G) | RFP §17's 3-second budget |
| X8 | Offline, then back online | Must fail clearly, not silently |
| X9 | Back/forward between screens | No stale page, no resubmitted POST |
| X10 | Tap accuracy on adjacent controls | 44px measured ≠ 44px comfortable |

## Security spot-checks on real hardware

These are covered by tests; confirming them on a device catches a proxy, cache,
or CDN layer that the test client never sees.

| # | Check | Expected |
|---|---|---|
| S1 | Edit the URL to another child's id | 404, not 403, and no data (RFP §21.4) |
| S2 | Copy a signed media URL and open it after ~5 minutes | Expired |
| S3 | Open a media URL while logged out | Refused |
| S4 | Confirm no photo is reachable at a guessable path | CLAUDE.md §1.4 |

## Sign-off

Do not tick this until every D1 and D2 row above is ticked by a person.

- [ ] D1 iPhone Safari — tester: ________ date: ________
- [ ] D2 Android Chrome — tester: ________ date: ________
- [ ] D3 Desktop Chrome — tester: ________ date: ________
- [ ] D4 Desktop Safari — tester: ________ date: ________

**Defects found go in a list below this line, not into this table.**

# Screenshotting the running app

Drives real Chromium against the development server, so what you see is what
a browser renders — not what the markup says.

```bash
npm install playwright && npx playwright install chromium
node scripts/screenshots/shoot.mjs <role> <name> <path> [width]

node scripts/screenshots/shoot.mjs anon login /nevtreh/
node scripts/screenshots/shoot.mjs teacher dashboard /bagsh/ 375
node scripts/screenshots/shoot.mjs director users /udirdlaga/hereglegch/
```

Roles are `anon`, `teacher`, `parent`, `director`, and they log in with the
`seed_demo` accounts, so run `make seed` first.

**WeasyPrint is not a substitute.** It was the first attempt: it is a print
engine, so it renders the CSRF token and the debug toolbar a browser hides,
and it ignores `@media` entirely — every responsive rule in `app.css` is
invisible to it.

Found on the first run: `input[type=password]` was missing from `app.css`, so
every password box in the product rendered as a browser default, and five
submit buttons had no `.btn`. Neither is visible in the template source.

The debug toolbar is hidden before interacting because at 375px its panel
list covers the login button. That is development-only — `debug_toolbar` is
added in `config/settings/dev.py` and is not installed in production.

Shots land in the scratchpad, not the repository. RFP §21.9 wants the layout
checked on a real device; this narrows what is left to check, it does not
replace it.

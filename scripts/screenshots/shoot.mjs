// Screenshot the running app the way a browser sees it.
//
// WeasyPrint was the first attempt and it lies: it is a print engine, so it
// renders the CSRF token and the debug toolbar that a browser hides, and it
// ignores @media queries. This drives real Chromium against the dev server.
//
// Usage: node shoot.mjs <role> <name> <path> [width]
//   node shoot.mjs anon login /nevtreh/
//   node shoot.mjs director dashboard /hyanalt/

import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const [, , role, name, path, widthArg] = process.argv;
const width = Number(widthArg ?? 1440);
const BASE = 'http://localhost:8000';
// Kept out of the repository: these are throwaway artefacts, and a
// directory of PNGs in git review is noise.
const OUT = process.env.SHOT_DIR ?? '/tmp/kinder-shots';

const LOGINS = {
  director: { id: 'director', pw: 'Demo-Nuuts99' },
  teacher: { id: 'teacher1', pw: 'Demo-Nuuts99' },
  parent: { id: '99110002', pw: 'Demo-Nuuts99' },
};

const HIDE_TOOLBAR = '#djDebug, #djDebugToolbarHandle, #djDebugToolbar { display: none !important; }';

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width, height: 1000 },
  deviceScaleFactor: 2,
  locale: 'mn-MN',
});
const page = await ctx.newPage();

if (role !== 'anon') {
  const who = LOGINS[role];
  if (!who) throw new Error(`unknown role: ${role}`);
  await page.goto(`${BASE}/nevtreh/`, { waitUntil: 'load' });
  // The debug toolbar is dev-only (config/settings/dev.py) but at 375px its
  // panel list covers the submit button, so hide it before interacting.
  await page.addStyleTag({ content: HIDE_TOOLBAR });
  await page.fill('input[name="username"]', who.id);
  await page.fill('input[name="password"]', who.pw);
  // waitForNavigation races the click and loses at narrow widths. Click,
  // then wait for the URL to stop being the login page.
  await page.click('button[type="submit"]');
  await page.waitForURL(u => !u.pathname.includes('nevtreh'), { timeout: 15000 });
}

await page.goto(`${BASE}${path}`, { waitUntil: 'load' });
// The debug toolbar is a development artefact; hide it so the shot shows
// what a real user sees.
await page.addStyleTag({ content: HIDE_TOOLBAR });
await page.waitForTimeout(250);

const file = `${OUT}/${name}-${width}.png`;
await page.screenshot({ path: file, fullPage: true });
console.log(file);

await browser.close();

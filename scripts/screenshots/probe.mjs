// Layout probe — the QA loop for the presentation-layer redesign
// (docs/UI_AUDIT.md, brief §25's list of reference widths).
//
// Two things `shoot.mjs` next door cannot do:
//
//   * **Viewport screenshots, not fullPage.** A fullPage capture renders a
//     `position: fixed` element wherever the scroll happened to be, so the
//     parent's bottom navigation appeared halfway down the page and looked
//     like a layout bug that was not there. These are viewport-sized.
//   * **Measurements a screenshot cannot show.** Whether the page scrolls
//     sideways and which element causes it, which tap targets are under
//     44px (RFP §629-635), and which form controls are under 16px and will
//     make mobile Safari zoom and never zoom back.
//
// Usage: node scripts/screenshots/probe.mjs <role> <name> <path>
//        WIDTHS=375,768 node scripts/screenshots/probe.mjs parent p /etseg-eh/
//
// Development only. Needs the dev server up and `seed_demo` data.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const BASE = 'http://localhost:8000';
const OUT = process.env.SHOT_DIR ?? '/tmp/kinder-probe';
const LOGINS = {
  director: { id: 'director', pw: 'Demo-Nuuts99' },
  teacher: { id: 'teacher1', pw: 'Demo-Nuuts99' },
  parent: { id: '99110002', pw: 'Demo-Nuuts99' },
};
const HIDE = '#djDebug, #djDebugToolbarHandle, #djDebugToolbar { display: none !important; }';

const [, , role, name, path] = process.argv;
const widths = (process.env.WIDTHS ?? '375,390,768,1024,1440').split(',').map(Number);

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

for (const width of widths) {
  const ctx = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 2, locale: 'mn-MN',
  });

  // The debug toolbar is hidden *before the first paint*, not after load.
  // `addStyleTag` after `goto` was measuring a layout the toolbar was still
  // part of: on 2026-08-17 it reported 107px of horizontal overflow on a
  // page that had none, and the element blamed was its own `<code>` block.
  // A QA tool that invents defects is worse than no QA tool.
  await ctx.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent =
        '#djDebug,#djDebugToolbarHandle,#djDebugToolbar{display:none!important}';
      document.head.appendChild(style);
    });
  });
  const page = await ctx.newPage();
  if (role !== 'anon') {
    const who = LOGINS[role];
    await page.goto(`${BASE}/nevtreh/`, { waitUntil: 'load' });
    await page.addStyleTag({ content: HIDE });
    await page.fill('input[name="username"]', who.id);
    await page.fill('input[name="password"]', who.pw);
    await page.click('button[type="submit"]');
    await page.waitForURL(u => !u.pathname.includes('nevtreh'), { timeout: 15000 });
  }
  await page.goto(`${BASE}${path}`, { waitUntil: 'load' });
  await page.addStyleTag({ content: HIDE });
  await page.waitForTimeout(250);

  const report = await page.evaluate(() => {
    const de = document.documentElement;
    const overflow = de.scrollWidth - de.clientWidth;

    // Anything wider than the viewport is what causes sideways page scroll.
    const wide = [...document.querySelectorAll('body *')]
      .filter(el => el.getBoundingClientRect().width > de.clientWidth + 1)
      .slice(0, 6)
      .map(el => `${el.tagName.toLowerCase()}.${(el.className || '').toString().split(' ')[0]}`);

    // Touch targets: RFP §629-635 wants 44px.
    const small = [...document.querySelectorAll('a, button, input[type=submit]')]
      .filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.height < 44;
      })
      .slice(0, 8)
      .map(el => `${(el.textContent || '').trim().slice(0, 22)} = ${Math.round(el.getBoundingClientRect().height)}px`);

    // Form controls under 16px make mobile Safari zoom on focus and never
    // zoom back out. Only controls the user can *type or pick into* trigger
    // it, so checkboxes, radios, buttons and hidden inputs are excluded —
    // they were pure noise and buried the one control that really was too
    // small (the per-domain level select, found this way on 2026-08-16).
    const EXEMPT = new Set([
      'checkbox', 'radio', 'hidden', 'submit', 'button', 'reset', 'file', 'range', 'color',
    ]);
    const tiny = [...document.querySelectorAll('input, select, textarea')]
      .filter(el => !EXEMPT.has((el.type || '').toLowerCase()))
      .filter(el => parseFloat(getComputedStyle(el).fontSize) < 16)
      .map(el => `${el.name || el.type}=${getComputedStyle(el).fontSize}`);

    const bn = document.querySelector('.bottomnav');
    const mh = document.querySelector('.mhead');
    const photo = document.querySelector('.profile__photo');

    return {
      overflow, wide, small, tiny,
      bottomnav: bn ? `${getComputedStyle(bn).display} pos=${getComputedStyle(bn).position} bottom=${Math.round(bn.getBoundingClientRect().bottom)}` : 'absent',
      mhead: mh ? getComputedStyle(mh).display : 'absent',
      photo: photo ? `${Math.round(photo.getBoundingClientRect().width)}x${Math.round(photo.getBoundingClientRect().height)}` : 'absent',
      docHeight: Math.round(de.scrollHeight),
    };
  });

  console.log(`\n=== ${width}px ===`);
  console.log(JSON.stringify(report, null, 1));

  await page.screenshot({ path: `${OUT}/${name}-${width}.png` });
  await ctx.close();
}
await browser.close();

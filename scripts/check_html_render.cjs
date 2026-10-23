#!/usr/bin/env node
// Actual browser evidence. Requires a locally available Playwright installation.
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createHash } = require('node:crypto');
const { parseArgs } = require('node:util');

async function main() {
  const { values } = parseArgs({ options: { html: { type: 'string' }, out: { type: 'string' }, channel: { type: 'string' } } });
  if (!values.html || !values.out) throw new Error('Use --html FILE --out NEW_EVIDENCE_DIRECTORY');
  const { chromium } = require('playwright');
  const html = path.resolve(values.html), out = path.resolve(values.out);
  const bytes = await fs.readFile(html);
  await fs.mkdir(out, { recursive: false });
  const browser = await chromium.launch({ headless: true, ...(values.channel ? { channel: values.channel } : {}) });
  const results = [], errors = [];
  try {
    for (const scenario of [
      { name: 'desktop', width: 1440, height: 1000, js: true },
      { name: 'mobile', width: 390, height: 844, js: true },
      { name: 'no-js', width: 390, height: 844, js: false },
      { name: 'print', width: 1440, height: 1000, js: false },
    ]) {
      const context = await browser.newContext({ viewport: { width: scenario.width, height: scenario.height }, javaScriptEnabled: scenario.js });
      const page = await context.newPage();
      const failures = [], remote = [];
      page.on('pageerror', e => failures.push(e.message));
      page.on('requestfailed', request => failures.push(request.url()));
      await page.route(/^https?:\/\//, route => { remote.push(route.request().url()); return route.abort(); });
      await page.goto(pathToFileURL(html).href, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      if (scenario.name === 'print') await page.emulateMedia({ media: 'print' });
      const surface = await page.evaluate(() => {
        const shown = node => {
          const style = getComputedStyle(node), rect = node.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0;
        };
        const works = [...document.querySelectorAll('[data-writer-work]')].map(work => {
          const body = work.querySelector('[data-writer-body]'), heading = work.querySelector('[data-writer-title]');
          const paragraphs = [...work.querySelectorAll('[data-writer-body] p')];
          return { id: work.id, bodyVisible: !!body && shown(body),
            paragraphs: paragraphs.length, visibleParagraphs: paragraphs.filter(p => !p.textContent || shown(p)).length,
            titleVisible: !heading || shown(heading),
            titleOverlapsBody: !!heading && !!body && heading.getBoundingClientRect().bottom > body.getBoundingClientRect().top,
            text: paragraphs.map(p => p.textContent),
            smallestFont: Math.min(...paragraphs.map(p => parseFloat(getComputedStyle(p).fontSize))) };
        });
        return { documentWidth: document.documentElement.scrollWidth, viewportWidth: document.documentElement.clientWidth,
          works, brokenImages: [...document.images].filter(img => !img.complete || img.naturalWidth === 0).map(img => img.getAttribute('src')) };
      });
      if (surface.documentWidth > surface.viewportWidth + 1) failures.push('Page-level horizontal overflow');
      if (!surface.works.length) failures.push('No manuscript surface found');
      for (const work of surface.works) {
        if (!work.bodyVisible || !work.titleVisible || work.visibleParagraphs !== work.paragraphs) failures.push(`Hidden prose: ${work.id}`);
        if (work.titleOverlapsBody) failures.push(`Title overlaps prose: ${work.id}`);
        if (work.smallestFont < 14) failures.push(`Body below 14px: ${work.id}`);
      }
      failures.push(...surface.brokenImages.map(name => 'Broken image: ' + name));
      failures.push(...remote.map(name => 'Remote runtime dependency: ' + name));
      const anchors = [];
      if (scenario.name !== 'print') {
        for (const anchor of await page.locator('nav a[href^="#"]').all()) {
          const href = await anchor.getAttribute('href');
          await anchor.click();
          const actual = await page.evaluate(() => decodeURIComponent(location.hash));
          anchors.push({ href, actual });
          if (actual !== href) failures.push('Anchor failed: ' + href);
        }
        if (anchors.length) {
          await page.goto(pathToFileURL(html).href);
          await page.keyboard.press('Tab');
          const focused = await page.evaluate(() => document.activeElement?.tagName);
          if (focused !== 'A') failures.push('First navigation link is not keyboard reachable');
        }
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      const screenshot = path.join(out, scenario.name + '.png');
      await page.screenshot({ path: screenshot, fullPage: true });
      if (scenario.name === 'print') await page.pdf({ path: path.join(out, 'print.pdf'), format: 'A4', printBackground: true,
        margin: { top: '18mm', bottom: '18mm', left: '18mm', right: '18mm' } });
      results.push({ ...scenario, surface, anchors, screenshot, errors: failures });
      errors.push(...failures.map(message => scenario.name + ': ' + message));
      await context.close();
    }
  } finally { await browser.close(); }
  const digest = data => createHash('sha256').update(data).digest('hex');
  if (digest(await fs.readFile(html)) !== digest(bytes)) errors.push('HTML changed during browser inspection');
  const evidence = [];
  for (const file of await fs.readdir(out)) evidence.push({ path: path.join(out, file), sha256: digest(await fs.readFile(path.join(out, file))) });
  const report = { status: errors.length ? 'render-checks-failed' : 'render-checks-passed', html, html_sha256: digest(bytes),
    results, errors, evidence, boundary: 'Actual browser measurements and screenshots; inspect screenshots for remaining layout problems. Not literary review or human preference evidence.' };
  await fs.writeFile(path.join(out, 'render-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, errors, report: path.join(out, 'render-check.json') }));
  process.exitCode = errors.length ? 1 : 0;
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });

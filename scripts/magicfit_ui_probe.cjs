const { chromium } = require('/work/node_modules/playwright');
const fs = require('fs');
const path = require('path');

function loadEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = value;
  }
}

async function main() {
  loadEnv('/docker/chummercomplete/chummer.run-services/.env');
  const outDir = '/docker/chummercomplete/_completion/magicfit_jama6_promo_12_scenes/probe';
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const events = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('magicfit') || url.includes('pushowl')) {
      events.push({ status: response.status(), url: url.slice(0, 240), contentType: response.headers()['content-type'] || '' });
    }
  });
  await page.goto('https://magicfit.pushowl.com/home', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(5000);
  await page.screenshot({ path: path.join(outDir, '01-home.png'), fullPage: true });
  const body1 = await page.locator('body').innerText({ timeout: 10000 }).catch(() => '');
  if (/login|sign in|email|password/i.test(body1)) {
    const email = process.env.CHUMMER_EA_MAGICFIT_EMAIL || '';
    const password = process.env.CHUMMER_EA_MAGICFIT_PASSWORD || '';
    const emailField = page.locator('input[type=email], input[name*=email i], input[placeholder*=email i]').first();
    if (await emailField.count()) await emailField.fill(email);
    const passwordField = page.locator('input[type=password]').first();
    if (await passwordField.count()) await passwordField.fill(password);
    const submit = page.getByRole('button', { name: /sign in|login|continue|submit/i }).first();
    if (await submit.count()) await submit.click();
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForTimeout(8000);
  }
  await page.screenshot({ path: path.join(outDir, '02-after-login.png'), fullPage: true });
  await page.goto('https://magicfit.pushowl.com/agents/generate?mode=video', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: path.join(outDir, '03-generate-video.png'), fullPage: true });
  const links = await page.locator('a').evaluateAll((nodes) => nodes.map((a) => ({ text: (a.innerText || a.textContent || '').trim(), href: a.href })).slice(0, 100)).catch(() => []);
  const buttons = await page.locator('button').evaluateAll((nodes) => nodes.map((b) => (b.innerText || b.textContent || '').trim()).filter(Boolean).slice(0, 100)).catch(() => []);
  const inputs = await page.locator('input, textarea, [contenteditable=true]').evaluateAll((nodes) => nodes.map((n) => ({ tag: n.tagName, type: n.getAttribute('type') || '', placeholder: n.getAttribute('placeholder') || '', text: (n.innerText || n.textContent || '').slice(0, 100) })).slice(0, 100)).catch(() => []);
  const html = await page.content().catch(() => '');
  fs.writeFileSync(path.join(outDir, 'generate-video.html'), html);
  fs.writeFileSync(path.join(outDir, 'probe.json'), JSON.stringify({ url: page.url(), title: await page.title(), body: (await page.locator('body').innerText().catch(() => '')).slice(0, 9000), links, buttons, inputs, events: events.slice(-160) }, null, 2));
  await browser.close();
  console.log(path.join(outDir, 'probe.json'));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

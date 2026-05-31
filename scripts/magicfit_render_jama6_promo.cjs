const { chromium } = require('/work/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const OUT_DIR = '/docker/chummercomplete/_completion/magicfit_jama6_promo_12_scenes';
const ENV_FILES = [
  '/docker/chummercomplete/chummer.run-services/.env',
  '/docker/EA/.env',
];

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

for (const file of ENV_FILES) loadEnv(file);

const GLOBAL_NEGATIVE = [
  'no factions',
  'no faction logos',
  'no faction recruitment ads',
  'no Shadowrun sourcebook text',
  'no copied rulebook pages',
  'no flat vector graphics',
  'no corporate SaaS explainer look',
  'no unreadable UI text',
  'no watermark',
].join(', ');

const SCENES = [
  {
    id: '01_old_way_pain',
    title: 'The old way is pain',
    duration: 6,
    prompt: 'Photoreal cinematic cyberpunk safehouse at night, rain on windows, cluttered tabletop with paper character sheets and old laptops, diverse shadowrunner-style RPG team frustrated by scattered notes, expressive acting, comic timing, handheld camera energy, moody practical lighting, premium movie trailer look.',
  },
  {
    id: '02_chummer6_reveal',
    title: 'Chummer6 enters',
    duration: 6,
    prompt: 'Photoreal product hero reveal in the same rainy cyberpunk safehouse, a focused decker opens a sleek dark desktop client named Chummer6, clean compact JAMA 5 style interface glow reflected on faces, team shifts from chaos to relief, cinematic push-in, premium software trailer energy.',
  },
  {
    id: '03_build_runner',
    title: 'Build your runner',
    duration: 8,
    prompt: 'Photoreal over-the-shoulder desktop workflow montage, compact character builder UI for a cyberpunk RPG, attributes, skills, cyberware, spells, gear and derived stats updating in a dense Windows desktop client, mouse-driven edits, practical monitor light, sharp premium commercial cinematography.',
  },
  {
    id: '04_explain_values',
    title: 'Explain every value',
    duration: 8,
    prompt: 'Photoreal cinematic product demo, elf mage user clicks an Explain button in Chummer6, a clean side panel shows a derived value breakdown as abstract readable blocks without copyrighted source text, the user nods, compact desktop interface, elegant motion and restrained dark UI.',
  },
  {
    id: '05_black_ledger_alive',
    title: 'Black Ledger is alive',
    duration: 8,
    prompt: 'Photoreal cyberpunk command room with a massive high-end rotating Earth globe interface, glowing cities, heat arcs, incident markers and risk pulses, no faction branding, team watching world pressure come alive, dramatic reveal, strategy-game scale, cinematic orbiting camera.',
  },
  {
    id: '06_release_truth',
    title: 'Release truth',
    duration: 8,
    prompt: 'Photoreal premium operations dashboard inside Chummer6, release truth matrix, provider receipts, proof freshness and audit gates visualized as clean compact status rows, no faction material, no marketing fluff, a developer and GM review green proof receipts with mouse pointer focus, serious release-control atmosphere.',
  },
  {
    id: '07_table_pulse',
    title: 'Table Pulse',
    duration: 8,
    prompt: 'Photoreal tabletop RPG session in progress, players around a real table with dice, maps and laptops, GM screen receives subtle Chummer6 Table Pulse alert showing heat and consequence as abstract UI, expressive reactions, cinematic closeups, warm table light and cyberpunk accents.',
  },
  {
    id: '08_world_reacts',
    title: 'The world reacts back',
    duration: 8,
    prompt: 'Photoreal split-scene cyberpunk gameplay moment, remote player on phone receives a stylish campaign reaction notification, taps a response, GM desktop receives a clean world-reaction receipt, product feature focus, crisp minimal UI overlays, cinematic tension, no faction identities.',
  },
  {
    id: '09_karma_forge',
    title: 'Karma Forge',
    duration: 8,
    prompt: 'Photoreal premium product scene focused on Karma Forge governance inside Chummer6, proposal, vote, comparison, review and approval flow in a compact desktop client, bad idea rejected with visible but abstract UI state, cast reacts, grounded elegant product cinematography.',
  },
  {
    id: '10_newsroom',
    title: 'Newsreels',
    duration: 8,
    prompt: 'Photoreal premium futuristic newsroom, charismatic ork news anchor delivers satirical fallout of a tabletop run, giant incident screens and ticker style visuals behind anchor, polished broadcast lighting, true TV-news framing, no canon logos, no faction content.',
  },
  {
    id: '11_play_anywhere',
    title: 'Play anywhere',
    duration: 6,
    prompt: 'Photoreal device continuity montage showing Chummer6 runner and campaign state moving from compact Windows desktop client to tablet and phone PWA, same data preserved, mouse and touch interactions visible, restrained premium UI, crisp transitions, no marketing page look.',
  },
  {
    id: '12_hero_ending',
    title: 'Chummer6 hero ending',
    duration: 8,
    prompt: 'Photoreal cinematic hero ending on rainy neon cyberpunk city street at night, recurring RPG team walks out confident after using Chummer6, reflections, chrome, subtle holographic glow, final product-title energy for Chummer6, emotional but witty finish, premium trailer quality.',
  },
];

function scenePath(scene, suffix) {
  return path.join(OUT_DIR, `${scene.id}${suffix}`);
}

async function login(page) {
  await page.goto('https://magicfit.pushowl.com/home', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(4000);
  const body = await page.locator('body').innerText({ timeout: 10000 }).catch(() => '');
  if (!/login|sign in|email|password/i.test(body)) return;
  const email = process.env.CHUMMER_EA_MAGICFIT_EMAIL || process.env.MAGICFIT_EMAIL || '';
  const password = process.env.CHUMMER_EA_MAGICFIT_PASSWORD || process.env.MAGICFIT_PASSWORD || '';
  if (!email || !password) throw new Error('MagicFit credentials are missing from env.');
  const emailField = page.locator('input[type=email], input[name*=email i], input[placeholder*=email i]').first();
  if (await emailField.count()) await emailField.fill(email);
  const passwordField = page.locator('input[type=password]').first();
  if (await passwordField.count()) await passwordField.fill(password);
  const submit = page.getByRole('button', { name: /sign in|login|continue|submit/i }).first();
  if (await submit.count()) await submit.click();
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(8000);
}

async function selectPill(page, currentText, optionText) {
  const pill = page.getByRole('button', { name: currentText }).last();
  await pill.click({ timeout: 10000 });
  await page.waitForTimeout(500);
  const option = page.getByText(optionText, { exact: true }).last();
  await option.click({ timeout: 10000 });
  await page.waitForTimeout(500);
}

async function fillPrompt(page, prompt) {
  const box = page.locator('[contenteditable="true"][role="textbox"]').first();
  await box.click({ timeout: 10000 });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.insertText(prompt);
  await page.waitForTimeout(800);
}

function download(url, file) {
  return new Promise((resolve, reject) => {
    const out = fs.createWriteStream(file);
    https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        out.close();
        fs.unlinkSync(file);
        return download(res.headers.location, file).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        out.close();
        fs.unlinkSync(file);
        reject(new Error(`download ${url} failed with ${res.statusCode}`));
        return;
      }
      res.pipe(out);
      out.on('finish', () => out.close(resolve));
    }).on('error', (error) => {
      out.close();
      try { fs.unlinkSync(file); } catch {}
      reject(error);
    });
  });
}

function collectCdnVideoUrlsFromText(text) {
  return [...new Set((text.match(/https:\/\/cdn\.pushowl\.com\/magicfit\/[^"'\s<>]+?\.(?:mp4|webm)/g) || [])
    .map((url) => url.replace(/\\u0026/g, '&').replace(/[),\]]+$/, '')))];
}

async function renderScene(page, scene) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const mp4Path = scenePath(scene, '.mp4');
  const sidecarPath = scenePath(scene, '.magicfit.json');
  if (fs.existsSync(mp4Path) && fs.existsSync(sidecarPath) && !process.argv.includes('--force')) {
    console.log(`skip ${scene.id}`);
    return;
  }

  const events = [];
  const seenVideoUrls = new Set();
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('magicfit') && !url.includes('pushowl')) return;
    const item = { status: response.status(), url, contentType: response.headers()['content-type'] || '' };
    events.push(item);
    if (/cdn\.pushowl\.com\/magicfit\/.*\.(mp4|webm)(?:$|\?)/.test(url)) seenVideoUrls.add(url);
    const ct = item.contentType;
    if (/json|script|text/.test(ct)) {
      const text = await response.text().catch(() => '');
      for (const found of collectCdnVideoUrlsFromText(text)) seenVideoUrls.add(found);
    }
  });

  await page.goto('https://magicfit.pushowl.com/agents/generate?mode=video', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(5000);
  await selectPill(page, '9:16', 'Landscape (16:9)').catch(async () => {
    await page.locator('select').nth(0).selectOption('16:9').catch(() => {});
  });
  await selectPill(page, '4s', `${scene.duration}s`).catch(async () => {
    await page.locator('select').nth(1).selectOption(String(scene.duration)).catch(() => {});
  });
  const fullPrompt = `${scene.prompt} Global constraints: ${GLOBAL_NEGATIVE}.`;
  await fillPrompt(page, fullPrompt);
  await page.screenshot({ path: scenePath(scene, '.before-submit.png'), fullPage: true });
  const submit = page.locator('form button').last();
  await submit.click({ timeout: 30000 });
  console.log(`submitted ${scene.id}`);
  await page.waitForTimeout(3000);

  const deadline = Date.now() + 18 * 60 * 1000;
  let videoUrl = null;
  while (Date.now() < deadline && !videoUrl) {
    await page.waitForTimeout(10000);
    const html = await page.content().catch(() => '');
    for (const found of collectCdnVideoUrlsFromText(html)) seenVideoUrls.add(found);
    const videos = await page.locator('video').evaluateAll((nodes) => nodes.map((v) => v.currentSrc || v.src).filter(Boolean)).catch(() => []);
    for (const found of videos) {
      if (/cdn\.pushowl\.com\/magicfit\/.*\.(mp4|webm)/.test(found)) seenVideoUrls.add(found);
    }
    videoUrl = [...seenVideoUrls].find((url) => /\.(mp4)(?:$|\?)/.test(url)) || [...seenVideoUrls][0] || null;
    if (!videoUrl) console.log(`poll ${scene.id}: waiting`);
  }
  await page.screenshot({ path: scenePath(scene, '.after-render.png'), fullPage: true }).catch(() => {});
  if (!videoUrl) {
    fs.writeFileSync(scenePath(scene, '.failed.json'), JSON.stringify({ scene, events: events.slice(-200), url: page.url() }, null, 2));
    throw new Error(`No MagicFit video URL found for ${scene.id}`);
  }
  await download(videoUrl, mp4Path);
  const sidecar = {
    provider: 'MagicFit',
    rendered_by: 'EA MagicFit browser automation',
    scene_id: scene.id,
    title: scene.title,
    duration_seconds_requested: scene.duration,
    aspect_ratio: '16:9',
    resolution: '720p',
    model: 'Seedance 2.0 Fast',
    video_output_url: videoUrl,
    source_prompt: fullPrompt,
    faction_assets_used: false,
    direct_publish: false,
    generated_at_utc: new Date().toISOString(),
    page_url_after_submit: page.url(),
    event_tail: events.slice(-80),
  };
  fs.writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2));
  console.log(`rendered ${scene.id} -> ${mp4Path}`);
}

async function main() {
  const onlyIdx = process.argv.indexOf('--only');
  const only = onlyIdx >= 0 ? new Set(process.argv[onlyIdx + 1].split(',').map((s) => s.trim())) : null;
  const scenes = only ? SCENES.filter((scene) => only.has(scene.id) || only.has(scene.id.slice(0, 2))) : SCENES;
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  const page = await context.newPage();
  await login(page);
  for (const scene of scenes) {
    await renderScene(page, scene);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

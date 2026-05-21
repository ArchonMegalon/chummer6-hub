const GLOBE_WORLD_ID = 'emerald-sprawl-prelude';
const BASE_MAP_WIDTH = 1200;
const BASE_MAP_HEIGHT = 760;
const TWO_PI = Math.PI * 2;

function slugify(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/_/g, '-')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/--+/g, '-')
    .replace(/^-|-$/g, '');
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function hexToRgba(hex, alpha) {
  const clean = String(hex || '#5ce2ff').replace('#', '');
  const source = clean.length === 3
    ? clean.split('').map((part) => part + part).join('')
    : clean.padEnd(6, '0').slice(0, 6);
  const red = Number.parseInt(source.slice(0, 2), 16);
  const green = Number.parseInt(source.slice(2, 4), 16);
  const blue = Number.parseInt(source.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function xToLon(x) {
  return (x / BASE_MAP_WIDTH) * 360 - 180;
}

function yToLat(y) {
  return 90 - (y / BASE_MAP_HEIGHT) * 180;
}

function latLonToVector(lat, lon, radius) {
  const latRad = (lat * Math.PI) / 180;
  const lonRad = (lon * Math.PI) / 180;
  return {
    x: radius * Math.cos(latRad) * Math.sin(lonRad),
    y: radius * Math.sin(latRad),
    z: radius * Math.cos(latRad) * Math.cos(lonRad),
  };
}

function rotateVector(vector, yaw, pitch) {
  const sinYaw = Math.sin(yaw);
  const cosYaw = Math.cos(yaw);
  const sinPitch = Math.sin(pitch);
  const cosPitch = Math.cos(pitch);
  const x1 = vector.x * cosYaw - vector.z * sinYaw;
  const z1 = vector.x * sinYaw + vector.z * cosYaw;
  const y2 = vector.y * cosPitch - z1 * sinPitch;
  const z2 = vector.y * sinPitch + z1 * cosPitch;
  return { x: x1, y: y2, z: z2 };
}

function makeButton(label, className, attributes = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = className;
  button.textContent = label;
  Object.entries(attributes).forEach(([key, value]) => button.setAttribute(key, String(value)));
  return button;
}

function seedFromString(value) {
  let hash = 2166136261;
  const text = String(value ?? '');
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function drawArrowHead(ctx, x, y, angle, size, color) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(size, 0);
  ctx.lineTo(-size * 0.85, size * 0.55);
  ctx.lineTo(-size * 0.85, -size * 0.55);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

class BlackLedgerGeoscapeRoot {
  constructor(root) {
    this.root = root;
    this.variant = root.dataset.variant || 'full';
    this.mapUrl = root.dataset.mapUrl || `/api/v1/ledger/worlds/${GLOBE_WORLD_ID}/map`;
    this.deltaUrl = root.dataset.deltaUrl || `/api/v1/ledger/worlds/${GLOBE_WORLD_ID}/map/tick-delta/0/1`;
    this.selectedFactionSlug = slugify(root.dataset.selectedFaction || '');
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.state = {
      mode: root.dataset.initialMode || 'influence',
      hoveredFaction: '',
      selectedFaction: this.selectedFactionSlug,
      replayState: 'idle',
      replayIndex: 0,
      tickHeadline: root.dataset.tickHeadline || 'Turn 1 pressure live.',
    };
    this.frame = null;
    this.canvas = null;
    this.ctx = null;
    this.panelTag = null;
    this.panelTitle = null;
    this.panelSummary = null;
    this.panelMetrics = null;
    this.panelActions = null;
    this.statusLine = null;
    this.fallbackList = null;
    this.tooltip = null;
    this.tooltipTag = null;
    this.tooltipTitle = null;
    this.tooltipBody = null;
    this.modeButtons = [];
    this.replayButton = null;
    this.regionMap = new Map();
    this.factionNodes = [];
    this.events = [];
    this.arcs = [];
    this.currentData = null;
    this.deltaData = null;
    this.hitNodes = [];
    this.rotation = -0.52;
    this.tilt = -0.2;
    this.lastTimestamp = 0;
  }

  syncModeState() {
    this.root.dataset.currentMode = this.state.mode;
    const mapShell = this.root.closest('.ledger-command-map');
    if (mapShell) {
      mapShell.dataset.currentMode = this.state.mode;
    }
  }

  async init() {
    this.mount();
    try {
      const [mapDocument, deltaDocument] = await Promise.all([
        fetch(this.mapUrl, { credentials: 'same-origin' }).then((response) => (response.ok ? response.json() : Promise.reject(new Error(`Map request failed: ${response.status}`)))),
        fetch(this.deltaUrl, { credentials: 'same-origin' }).then((response) => (response.ok ? response.json() : null)),
      ]);
      this.currentData = mapDocument;
      this.deltaData = deltaDocument;
      this.state.mode = this.resolveMode(this.state.mode, mapDocument.modes);
      this.syncModeState();
      this.root.dataset.replayState = 'idle';
      this.buildModel();
      this.renderControls();
      this.renderFallbackList();
      this.attachEvents();
      this.selectInitialFaction();
      this.root.dataset.renderer = 'canvas-geoscape';
      this.root.dataset.reducedMotion = this.reducedMotion ? 'true' : 'false';
      this.root.dataset.ready = 'true';
      if (this.root.dataset.autoReplay === 'true') {
        this.playReplay();
      } else {
        this.updatePanel();
        this.renderFrame();
      }
      this.startLoop();
    } catch (error) {
      console.error(error);
      this.root.dataset.ready = 'false';
      this.root.dataset.renderer = 'fallback';
      if (this.statusLine) {
        this.statusLine.textContent = 'Globe fallback engaged. Tactical backup stays active below.';
      }
      this.root.classList.add('is-fallback');
    }
  }

  resolveMode(mode, modes) {
    return modes?.some((entry) => entry.id === mode) ? mode : (modes?.[0]?.id || 'influence');
  }

  mount() {
    this.root.classList.add('black-ledger-geoscape');
    this.root.innerHTML = `
      <div class="black-ledger-geoscape__shell black-ledger-geoscape__shell--${this.variant}">
        <div class="black-ledger-geoscape__stage">
          <canvas class="black-ledger-geoscape__canvas" role="img" aria-label="Black Ledger command globe"></canvas>
          <div class="black-ledger-geoscape__overlay">
            <div class="black-ledger-geoscape__eyebrow">Black Ledger command globe</div>
            <div class="black-ledger-geoscape__headline">${this.variant === 'teaser' ? 'Turn 1 already ran.' : 'Pressure is crossing the board.'}</div>
            <div class="black-ledger-geoscape__status"></div>
          </div>
          <div class="black-ledger-geoscape__tooltip" aria-hidden="true">
            <span class="tag black-ledger-geoscape__tooltip-tag">Faction pressure</span>
            <strong class="black-ledger-geoscape__tooltip-title">Loading…</strong>
            <p class="black-ledger-geoscape__tooltip-body">Preparing faction posture.</p>
          </div>
        </div>
        <aside class="black-ledger-geoscape__panel" aria-live="polite">
          <span class="tag black-ledger-geoscape__panel-tag">Faction pressure</span>
          <h3 class="black-ledger-geoscape__panel-title">Loading geoscape…</h3>
          <p class="black-ledger-geoscape__panel-summary">Pulling the public-safe world state.</p>
          <div class="black-ledger-geoscape__panel-metrics"></div>
          <div class="black-ledger-geoscape__panel-actions"></div>
        </aside>
      </div>
      <div class="black-ledger-geoscape__controls">
        <div class="black-ledger-geoscape__modes" role="tablist" aria-label="Geoscape modes"></div>
        <div class="black-ledger-geoscape__playback">
          <button type="button" class="black-ledger-geoscape__replay button-like button-like--secondary">Replay pressure</button>
        </div>
      </div>
      <div class="black-ledger-geoscape__fallback-list" aria-label="Accessible geoscape list"></div>
    `;

    this.canvas = this.root.querySelector('.black-ledger-geoscape__canvas');
    this.ctx = this.canvas.getContext('2d');
    this.panelTag = this.root.querySelector('.black-ledger-geoscape__panel-tag');
    this.panelTitle = this.root.querySelector('.black-ledger-geoscape__panel-title');
    this.panelSummary = this.root.querySelector('.black-ledger-geoscape__panel-summary');
    this.panelMetrics = this.root.querySelector('.black-ledger-geoscape__panel-metrics');
    this.panelActions = this.root.querySelector('.black-ledger-geoscape__panel-actions');
    this.statusLine = this.root.querySelector('.black-ledger-geoscape__status');
    this.fallbackList = this.root.querySelector('.black-ledger-geoscape__fallback-list');
    this.tooltip = this.root.querySelector('.black-ledger-geoscape__tooltip');
    this.tooltipTag = this.root.querySelector('.black-ledger-geoscape__tooltip-tag');
    this.tooltipTitle = this.root.querySelector('.black-ledger-geoscape__tooltip-title');
    this.tooltipBody = this.root.querySelector('.black-ledger-geoscape__tooltip-body');
    this.replayButton = this.root.querySelector('.black-ledger-geoscape__replay');
    this.syncCanvasSize();
    window.addEventListener('resize', () => this.syncCanvasSize(), { passive: true });
  }

  syncCanvasSize() {
    if (!this.canvas) {
      return;
    }

    const stage = this.root.querySelector('.black-ledger-geoscape__stage');
    const bounds = stage.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.max(320, Math.floor(bounds.width * ratio));
    this.canvas.height = Math.max(300, Math.floor(bounds.height * ratio));
    this.canvas.style.width = `${Math.max(320, Math.floor(bounds.width))}px`;
    this.canvas.style.height = `${Math.max(300, Math.floor(bounds.height))}px`;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(ratio, ratio);
    this.renderFrame();
  }

  buildModel() {
    const data = this.currentData;
    const regionById = new Map();
    data.regions.forEach((region) => {
      const lat = yToLat(region.centerY);
      const lon = xToLon(region.centerX);
      regionById.set(region.regionId, { ...region, lat, lon, slug: slugify(region.regionId) });
    });
    this.regionMap = regionById;

    this.factionNodes = data.factions.map((faction, index) => {
      const regions = data.regions.filter((region) => slugify(region.dominantFactionId) === slugify(faction.factionId));
      const centerX = regions.length > 0
        ? regions.reduce((sum, region) => sum + region.centerX, 0) / regions.length
        : 180 + index * 150;
      const centerY = regions.length > 0
        ? regions.reduce((sum, region) => sum + region.centerY, 0) / regions.length
        : 200 + (index % 2) * 160;
      const influence = regions.reduce((sum, region) => sum + region.influence, 0);
      const heat = regions.reduce((sum, region) => sum + region.heat, 0);
      const volatility = regions.reduce((sum, region) => sum + region.volatility, 0);
      const pressureScore = Math.max(1, Math.round((influence + heat + volatility) / Math.max(1, regions.length)));
      return {
        ...faction,
        slug: slugify(faction.factionId),
        lat: yToLat(centerY),
        lon: xToLon(centerX),
        influenceRadius: clamp(0.4 + pressureScore / 160, 0.42, 0.88),
        regionCount: regions.length,
        heat,
        pressureScore,
        volatility,
        seed: seedFromString(faction.factionId),
      };
    });

    this.events = data.events.map((event) => {
      const region = regionById.get(event.regionId);
      return {
        ...event,
        lat: region?.lat ?? yToLat(event.y),
        lon: region?.lon ?? xToLon(event.x),
      };
    });

    this.arcs = data.arcs.map((arc) => ({
      ...arc,
      source: regionById.get(arc.sourceRegionId),
      target: regionById.get(arc.targetRegionId),
    })).filter((arc) => arc.source && arc.target);
    this.root.dataset.factionCount = String(this.factionNodes.length);
    this.root.dataset.eventCount = String(this.events.length);
    this.root.dataset.arcCount = String(this.arcs.length);
    this.root.dataset.districtCount = String(data.regions.length);
  }

  renderControls() {
    const modeRail = this.root.querySelector('.black-ledger-geoscape__modes');
    modeRail.innerHTML = '';
    this.modeButtons = this.currentData.modes.map((mode) => {
      const button = makeButton(mode.label, `black-ledger-geoscape__mode-button${mode.id === this.state.mode ? ' is-active' : ''}`, {
        'data-mode': mode.id,
        'aria-pressed': mode.id === this.state.mode ? 'true' : 'false',
        title: mode.summary,
      });
      button.addEventListener('click', () => this.setMode(mode.id));
      modeRail.appendChild(button);
      return button;
    });
    if (this.variant === 'teaser') {
      this.root.querySelector('.black-ledger-geoscape__controls').classList.add('is-teaser');
    }
  }

  renderFallbackList() {
    if (!this.fallbackList) {
      return;
    }

    const intro = this.variant === 'onboarding'
      ? '<p class="muted-copy">Keyboard-safe faction chooser.</p>'
      : '<p class="muted-copy">Flagship fallback list for faction focus, hotspots, and pressure arrows.</p>';
    const factionItems = this.factionNodes.map((faction) => `
      <li>
        <button type="button" class="black-ledger-geoscape__list-button" data-faction-select="${faction.slug}" data-faction-id="${faction.slug}">
          <strong>${faction.name}</strong>
          <span>${faction.type} · ${faction.regionCount} districts · Heat ${Math.max(0, faction.heat)}</span>
        </button>
      </li>`).join('');
    const eventItems = this.events.slice(0, 4).map((event) => `<li><strong>${event.title}</strong><span>${event.summary}</span></li>`).join('');
    this.fallbackList.innerHTML = `
      ${intro}
      <div class="black-ledger-geoscape__list-grid">
        <section>
          <h4>Faction countries</h4>
          <ul class="black-ledger-geoscape__list">${factionItems}</ul>
        </section>
        <section>
          <h4>Pressure arrows</h4>
          <ul class="black-ledger-geoscape__list black-ledger-geoscape__list--static">${eventItems}</ul>
        </section>
      </div>
    `;
    this.fallbackList.querySelectorAll('[data-faction-select]').forEach((button) => {
      button.addEventListener('click', () => this.selectFaction(button.getAttribute('data-faction-select')));
    });
  }

  attachEvents() {
    this.replayButton?.addEventListener('click', () => this.playReplay());
    this.root.addEventListener('keydown', (event) => this.handleKeydown(event));
    this.canvas?.addEventListener('mousemove', (event) => this.handlePointer(event));
    this.canvas?.addEventListener('mouseleave', () => {
      this.state.hoveredFaction = '';
      this.hideTooltip();
      this.updatePanel();
    });
    this.canvas?.addEventListener('click', (event) => {
      const hit = this.hitTest(event);
      if (hit) {
        this.selectFaction(hit.slug);
      }
    });
  }

  handlePointer(event) {
    const hit = this.hitTest(event);
    this.canvas.style.cursor = hit ? 'pointer' : 'default';
    this.state.hoveredFaction = hit?.slug || '';
    if (hit) {
      this.showTooltip(hit, event);
    } else {
      this.hideTooltip();
    }
    this.updatePanel();
  }

  hitTest(event) {
    const bounds = this.canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    return this.hitNodes.find((node) => Math.hypot(node.x - x, node.y - y) <= node.radius + 12) || null;
  }

  showTooltip(hit, event) {
    if (!this.tooltip) {
      return;
    }
    const faction = this.factionNodes.find((item) => item.slug === hit.slug);
    if (!faction) {
      return;
    }
    this.tooltipTag.textContent = faction.type || 'Faction';
    this.tooltipTitle.textContent = faction.name;
    this.tooltipBody.textContent = `${faction.publicSummary} Pressure ${faction.pressureScore}. Heat ${Math.max(0, faction.heat)} across ${faction.regionCount} districts.`;
    const stageBounds = this.root.querySelector('.black-ledger-geoscape__stage').getBoundingClientRect();
    const localX = event.clientX - stageBounds.left;
    const localY = event.clientY - stageBounds.top;
    this.tooltip.style.setProperty('--tooltip-x', `${clamp(localX, 90, Math.max(90, stageBounds.width - 90))}px`);
    this.tooltip.style.setProperty('--tooltip-y', `${clamp(localY - 22, 60, Math.max(60, stageBounds.height - 60))}px`);
    this.tooltip.classList.add('is-visible');
    this.tooltip.setAttribute('aria-hidden', 'false');
  }

  hideTooltip() {
    if (!this.tooltip) {
      return;
    }
    this.tooltip.classList.remove('is-visible');
    this.tooltip.setAttribute('aria-hidden', 'true');
  }

  handleKeydown(event) {
    if (!this.factionNodes.length) {
      return;
    }

    const currentIndex = Math.max(0, this.factionNodes.findIndex((item) => item.slug === (this.state.selectedFaction || this.state.hoveredFaction)));
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault();
      const next = this.factionNodes[(currentIndex + 1) % this.factionNodes.length];
      this.selectFaction(next.slug);
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = this.factionNodes[(currentIndex - 1 + this.factionNodes.length) % this.factionNodes.length];
      this.selectFaction(next.slug);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      this.selectFaction(this.state.hoveredFaction || this.state.selectedFaction || this.factionNodes[0].slug);
    } else if (event.key === 'Escape') {
      this.state.selectedFaction = '';
      this.hideTooltip();
      this.updatePanel();
    } else if (event.key === ' ') {
      event.preventDefault();
      this.playReplay();
    }
  }

  selectInitialFaction() {
    if (this.selectedFactionSlug) {
      this.selectFaction(this.selectedFactionSlug);
      return;
    }

    const ashline = this.factionNodes.find((item) => item.slug === 'ashline-circle');
    if (ashline) {
      this.selectFaction(ashline.slug);
      return;
    }

    if (this.factionNodes[0]) {
      this.selectFaction(this.factionNodes[0].slug);
    }
  }

  selectFaction(slug) {
    this.state.selectedFaction = slugify(slug);
    const selected = this.factionNodes.find((item) => item.slug === this.state.selectedFaction);
    if (selected) {
      this.rotation = -((selected.lon * Math.PI) / 180);
      this.tilt = clamp(-((selected.lat * Math.PI) / 540), -0.5, 0.18);
    }
    this.root.dataset.selectedFaction = this.state.selectedFaction;
    this.updatePanel();
    this.renderFrame();
  }

  setMode(mode) {
    this.state.mode = mode;
    this.syncModeState();
    this.modeButtons.forEach((button) => {
      const active = button.getAttribute('data-mode') === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    this.root.dataset.renderSignature = `${mode}:${this.state.selectedFaction || 'none'}:${this.state.replayState}`;
    this.updatePanel();
    this.renderFrame();
  }

  async playReplay() {
    if (this.reducedMotion) {
      const next = (this.state.replayIndex + 1) % 4;
      this.state.replayIndex = next;
      this.state.replayState = ['idle', 'turn-0', 'turn-1-hotspots', 'turn-1-final'][next];
      this.root.dataset.replayState = this.state.replayState;
      this.updatePanel();
      this.renderFrame();
      return;
    }

    this.state.replayState = 'playing';
    this.root.dataset.replayState = 'playing';
    this.replayButton.textContent = 'Replaying…';
    const steps = ['turn-0', 'turn-1-hotspots', 'turn-1-arcs', 'turn-1-final'];
    for (let index = 0; index < steps.length; index += 1) {
      this.state.replayIndex = index;
      this.root.dataset.replayState = steps[index];
      this.updatePanel();
      this.renderFrame();
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => window.setTimeout(resolve, 850));
    }
    this.state.replayState = 'idle';
    this.root.dataset.replayState = 'idle';
    this.replayButton.textContent = 'Replay pressure';
    this.updatePanel();
  }

  updatePanel() {
    if (!this.panelTitle || !this.factionNodes.length) {
      return;
    }

    const selectedFaction = this.factionNodes.find((item) => item.slug === (this.state.hoveredFaction || this.state.selectedFaction));
    const highlightedEvent = this.events[this.state.replayState === 'turn-0' ? 0 : clamp(this.state.replayIndex, 0, Math.max(0, this.events.length - 1))];
    const activeFaction = selectedFaction || this.factionNodes[0];
    const relatedRegions = this.currentData.regions.filter((region) => slugify(region.dominantFactionId) === activeFaction.slug);
    const dispatchHref = highlightedEvent?.dispatchHref || '/ledger/dispatches';
    const defaultPrimaryHref = this.variant === 'onboarding'
      ? `#faction-join-${activeFaction.slug}`
      : `/ledger/factions/${activeFaction.slug}`;
    const defaultPrimaryLabel = this.variant === 'onboarding' ? 'Join this faction' : 'Open faction file';
    const defaultSecondaryHref = this.variant === 'onboarding'
      ? '/account/ledger/onboarding?step=choose-path'
      : `/ledger/factions/${activeFaction.slug}/promo`;
    const defaultSecondaryLabel = this.variant === 'onboarding' ? 'Found my own' : 'Open storyboard';
    const primaryHref = this.root.dataset.primaryHref || defaultPrimaryHref;
    const primaryLabel = this.root.dataset.primaryLabel || defaultPrimaryLabel;
    const secondaryHref = this.root.dataset.secondaryHref || defaultSecondaryHref;
    const secondaryLabel = this.root.dataset.secondaryLabel || defaultSecondaryLabel;

    if (this.state.replayState === 'turn-0') {
      this.panelTag.textContent = 'Turn 0 baseline';
      this.panelTitle.textContent = 'Before the arrows lit up';
      this.panelSummary.textContent = this.deltaData?.summary || 'Baseline faction countries before the first visible public pressure wave.';
    } else {
      this.panelTag.textContent = activeFaction.type || 'Faction pressure';
      this.panelTitle.textContent = activeFaction.name;
      this.panelSummary.textContent = this.variant === 'teaser'
        ? 'Turn 1 replay, faction countries, and pressure arrows continue inside Black Ledger.'
        : activeFaction.publicSummary;
    }

    const metrics = [
      `Mode: ${this.state.mode.replace('-', ' ')}`,
      `Countries: ${Math.max(1, relatedRegions.length)}`,
      `Pressure: ${activeFaction.pressureScore}`,
      highlightedEvent?.sourceReceiptId ? `Receipt: ${highlightedEvent.sourceReceiptId}` : `Turn: ${this.currentData.currentTurn}`,
    ];
    this.panelMetrics.innerHTML = metrics.map((metric) => `<span>${metric}</span>`).join('');

    this.panelActions.innerHTML = this.variant === 'teaser'
      ? '<span class="muted-copy">Faction countries, pressure arrows, and turn replay stay public-safe and route-backed.</span>'
      : `
        <a class="button-like button-like--primary" href="${primaryHref}">${primaryLabel}</a>
        <a class="button-like button-like--secondary" href="${secondaryHref}">${secondaryLabel}</a>
        <a class="inline-link" href="${dispatchHref}">Latest dispatch</a>
      `;

    if (this.statusLine) {
      const replayLabel = this.state.replayState === 'idle' ? 'idle globe' : this.root.dataset.replayState;
      this.statusLine.textContent = this.reducedMotion
        ? 'Reduced motion active. Replay advances step by step.'
        : `${this.state.tickHeadline} · ${this.state.mode.replace('-', ' ')} · ${replayLabel}`;
    }
    this.root.dataset.renderSignature = `${this.state.mode}:${activeFaction.slug}:${this.root.dataset.replayState || 'idle'}`;
  }

  startLoop() {
    const tick = (timestamp) => {
      const deltaSeconds = this.lastTimestamp === 0 ? 0 : (timestamp - this.lastTimestamp) / 1000;
      this.lastTimestamp = timestamp;
      if (!this.reducedMotion && this.state.replayState !== 'playing') {
        this.rotation += deltaSeconds * 0.08;
      }
      this.renderFrame(timestamp / 1000);
      this.frame = window.requestAnimationFrame(tick);
    };
    if (this.frame) {
      window.cancelAnimationFrame(this.frame);
    }
    this.frame = window.requestAnimationFrame(tick);
  }

  renderFrame(time = 0) {
    if (!this.ctx || !this.canvas || !this.currentData) {
      return;
    }

    const ctx = this.ctx;
    const width = parseFloat(this.canvas.style.width || '640');
    const height = parseFloat(this.canvas.style.height || '420');
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * (this.variant === 'teaser' ? 0.31 : 0.34);
    ctx.clearRect(0, 0, width, height);

    this.drawBackdrop(ctx, width, height, centerX, centerY, radius, time);
    ctx.save();
    ctx.translate(centerX, centerY);
    this.drawSphere(ctx, radius, time);
    this.drawArcs(ctx, radius, time);
    this.drawFactions(ctx, radius, time);
    this.drawEvents(ctx, radius, time);
    ctx.restore();
  }

  drawBackdrop(ctx, width, height, centerX, centerY, radius, time) {
    const gradient = ctx.createRadialGradient(centerX * 0.84, centerY * 0.54, radius * 0.18, centerX, centerY, radius * 2.1);
    gradient.addColorStop(0, 'rgba(46, 88, 132, 0.38)');
    gradient.addColorStop(0.48, 'rgba(8, 16, 27, 0.82)');
    gradient.addColorStop(1, 'rgba(2, 7, 12, 1)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    for (let index = 0; index < 26; index += 1) {
      const seed = seedFromString(`star-${index}`);
      const x = width * ((seed * 0.77 + index * 0.037) % 1);
      const y = height * ((seed * 0.33 + index * 0.051) % 1);
      const alpha = 0.12 + ((Math.sin(time * 0.7 + index) + 1) * 0.06);
      ctx.fillStyle = `rgba(214, 232, 255, ${alpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(x, y, 1.2 + (seed * 1.8), 0, TWO_PI);
      ctx.fill();
    }
  }

  drawSphere(ctx, radius, time) {
    const atmosphere = ctx.createRadialGradient(-radius * 0.3, -radius * 0.45, radius * 0.12, 0, 0, radius * 1.24);
    atmosphere.addColorStop(0, 'rgba(38, 104, 163, 0.98)');
    atmosphere.addColorStop(0.48, 'rgba(12, 42, 71, 0.98)');
    atmosphere.addColorStop(0.78, 'rgba(5, 17, 29, 1)');
    atmosphere.addColorStop(1, 'rgba(2, 8, 14, 1)');
    ctx.fillStyle = atmosphere;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, TWO_PI);
    ctx.fill();

    ctx.strokeStyle = 'rgba(110, 226, 255, 0.11)';
    ctx.lineWidth = 1;
    for (let index = 1; index <= 6; index += 1) {
      ctx.beginPath();
      ctx.ellipse(0, 0, radius, radius * Math.cos((index / 7) * (Math.PI / 2)), 0, 0, TWO_PI);
      ctx.stroke();
    }
    for (let index = 0; index < 10; index += 1) {
      ctx.save();
      ctx.rotate((index / 10) * Math.PI);
      ctx.beginPath();
      ctx.moveTo(0, -radius);
      ctx.quadraticCurveTo(radius * 0.26, 0, 0, radius);
      ctx.stroke();
      ctx.restore();
    }

    ctx.strokeStyle = 'rgba(92, 226, 255, 0.3)';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(0, 0, radius + 12, 0, TWO_PI);
    ctx.stroke();

    if (!this.reducedMotion) {
      ctx.strokeStyle = 'rgba(92, 226, 255, 0.1)';
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.arc(0, 0, radius + 24 + Math.sin(time * 1.25) * 4, 0, TWO_PI);
      ctx.stroke();
    }
  }

  project(lat, lon, radius) {
    const vector = latLonToVector(lat, lon, radius);
    const rotated = rotateVector(vector, this.rotation, this.tilt);
    const perspective = 1 + rotated.z / (radius * 3.1);
    return {
      x: rotated.x * perspective,
      y: rotated.y * perspective,
      z: rotated.z,
      visible: rotated.z > -radius * 0.25,
    };
  }

  drawFactionCountry(ctx, faction, projected, radius, time) {
    const baseRadius = radius * faction.influenceRadius * (faction.slug === this.state.selectedFaction ? 0.44 : 0.34);
    const wobble = this.reducedMotion ? 0 : Math.sin(time * 0.7 + faction.seed * 10) * 4;
    const pointCount = 9;
    ctx.beginPath();
    for (let index = 0; index <= pointCount; index += 1) {
      const ratio = index / pointCount;
      const angle = ratio * TWO_PI;
      const contourSeed = seedFromString(`${faction.slug}:${index}`);
      const localRadius = baseRadius * (0.76 + contourSeed * 0.44) + wobble;
      const x = projected.x + Math.cos(angle) * localRadius;
      const y = projected.y + Math.sin(angle) * localRadius * (0.72 + contourSeed * 0.18);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.closePath();

    const fill = ctx.createRadialGradient(projected.x - baseRadius * 0.35, projected.y - baseRadius * 0.5, 0, projected.x, projected.y, baseRadius * 1.2);
    fill.addColorStop(0, hexToRgba(faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.46 : 0.34));
    fill.addColorStop(1, hexToRgba(faction.colorSecondary || faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.14 : 0.1));
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = hexToRgba(faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.98 : 0.7);
    ctx.lineWidth = faction.slug === this.state.selectedFaction ? 2.4 : 1.3;
    ctx.stroke();
  }

  drawFactions(ctx, radius, time) {
    this.hitNodes = [];
    const centerOffsetX = this.canvas.clientWidth / 2;
    const centerOffsetY = this.canvas.clientHeight / 2;
    this.factionNodes.forEach((faction, index) => {
      const projected = this.project(faction.lat, faction.lon, radius * 0.92);
      if (!projected.visible) {
        return;
      }

      const selected = faction.slug === this.state.selectedFaction;
      const hovered = faction.slug === this.state.hoveredFaction;
      const pulse = this.reducedMotion ? 1 : (1 + Math.sin(time * 1.5 + index) * 0.08);
      this.drawFactionCountry(ctx, faction, projected, radius, time);

      const haloRadius = radius * faction.influenceRadius * (selected ? 0.36 : 0.25) * pulse;
      ctx.fillStyle = hexToRgba(faction.colorPrimary, selected ? 0.22 : hovered ? 0.18 : 0.12);
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, haloRadius, 0, TWO_PI);
      ctx.fill();

      ctx.fillStyle = hexToRgba(faction.colorPrimary, 1);
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, selected ? 8 : 6.5, 0, TWO_PI);
      ctx.fill();
      ctx.strokeStyle = 'rgba(239, 247, 255, 0.88)';
      ctx.lineWidth = selected ? 2.8 : 1.8;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, selected ? 13 : 10.5, 0, TWO_PI);
      ctx.stroke();

      ctx.fillStyle = 'rgba(233, 241, 249, 0.96)';
      ctx.font = selected ? '700 14px "IBM Plex Sans", sans-serif' : '700 12px "IBM Plex Sans", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(faction.name, projected.x, projected.y - haloRadius - 12);
      this.hitNodes.push({
        slug: faction.slug,
        x: projected.x + centerOffsetX,
        y: projected.y + centerOffsetY,
        radius: Math.max(18, haloRadius * 0.48),
      });
    });
  }

  drawEvents(ctx, radius, time) {
    const replayFilter = this.root.dataset.replayState;
    this.events.forEach((event, index) => {
      if (replayFilter === 'turn-0' && index > 0) {
        return;
      }
      if (replayFilter === 'turn-1-hotspots' && index > 2) {
        return;
      }

      const projected = this.project(event.lat, event.lon, radius * 0.985);
      if (!projected.visible) {
        return;
      }

      const eventMode = event.eventType === 'logistics'
        ? 'economy'
        : event.eventType === 'magic'
          ? 'magic'
          : event.eventType === 'intel'
            ? 'intel'
            : event.eventType === 'conflict'
              ? 'conflict'
              : 'recent-changes';
      const emphasized = this.state.mode === 'influence' || this.state.mode === 'recent-changes' || this.state.mode === eventMode;

      const pulse = this.reducedMotion ? 1 : (1 + Math.sin(time * 2.2 + index) * 0.14);
      const baseRadius = clamp(5 + event.severity / 18, 7, 15);
      ctx.globalAlpha = emphasized ? 1 : 0.28;
      ctx.fillStyle = event.eventType === 'magic'
        ? 'rgba(177, 133, 255, 0.95)'
        : event.eventType === 'logistics'
          ? 'rgba(89, 244, 186, 0.95)'
          : event.eventType === 'intel'
            ? 'rgba(222, 232, 244, 0.95)'
            : event.eventType === 'conflict'
              ? 'rgba(255, 88, 115, 0.95)'
              : 'rgba(255, 164, 88, 0.95)';
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, baseRadius, 0, TWO_PI);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.38)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, baseRadius + 6 * pulse, 0, TWO_PI);
      ctx.stroke();
      ctx.globalAlpha = 1;
    });
  }

  drawArcs(ctx, radius, time) {
    const replayFilter = this.root.dataset.replayState;
    this.arcs.forEach((arc, index) => {
      if (replayFilter === 'turn-0') {
        return;
      }
      if (replayFilter === 'turn-1-hotspots' && index > 1) {
        return;
      }

      const source = this.project(arc.source.lat, arc.source.lon, radius * 0.965);
      const target = this.project(arc.target.lat, arc.target.lon, radius * 0.965);
      if (!source.visible && !target.visible) {
        return;
      }

      const arcMode = arc.arcType === 'logistics'
        ? 'economy'
        : arc.arcType === 'debt'
          ? 'economy'
          : arc.arcType === 'magic'
            ? 'magic'
            : arc.arcType === 'intel'
              ? 'intel'
              : arc.arcType === 'conflict'
                ? 'conflict'
                : 'recent-changes';
      ctx.globalAlpha = this.state.mode === 'influence' || this.state.mode === 'recent-changes' || this.state.mode === arcMode ? 1 : 0.22;

      const midpointX = (source.x + target.x) / 2;
      const midpointY = (source.y + target.y) / 2 - clamp(26 + arc.intensity * 0.36, 32, 70);
      const stroke = arc.arcType === 'magic'
        ? 'rgba(172, 126, 255, 0.86)'
        : arc.arcType === 'logistics'
          ? 'rgba(89, 244, 186, 0.82)'
          : arc.arcType === 'intel'
            ? 'rgba(210, 225, 241, 0.78)'
            : arc.arcType === 'conflict'
              ? 'rgba(255, 89, 114, 0.84)'
              : 'rgba(255, 164, 88, 0.84)';
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1.6 + arc.intensity / 34;
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.quadraticCurveTo(midpointX, midpointY, target.x, target.y);
      ctx.stroke();

      const travel = this.reducedMotion ? 0.62 : (time * 0.18 + index * 0.11) % 1;
      const t = travel;
      const x = (1 - t) * (1 - t) * source.x + 2 * (1 - t) * t * midpointX + t * t * target.x;
      const y = (1 - t) * (1 - t) * source.y + 2 * (1 - t) * t * midpointY + t * t * target.y;
      const dx = 2 * (1 - t) * (midpointX - source.x) + 2 * t * (target.x - midpointX);
      const dy = 2 * (1 - t) * (midpointY - source.y) + 2 * t * (target.y - midpointY);
      drawArrowHead(ctx, x, y, Math.atan2(dy, dx), 8 + arc.intensity / 50, stroke);
      ctx.globalAlpha = 1;
    });
  }
}

function boot() {
  document.querySelectorAll('[data-black-ledger-geoscape-root]').forEach((root) => {
    const geoscape = new BlackLedgerGeoscapeRoot(root);
    geoscape.init();
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}

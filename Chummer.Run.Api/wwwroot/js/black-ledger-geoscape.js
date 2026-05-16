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
      tickHeadline: root.dataset.tickHeadline || 'Turn 1 already ran.',
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
    this.modeButtons = [];
    this.replayButton = null;
    this.regionMap = new Map();
    this.factionNodes = [];
    this.events = [];
    this.arcs = [];
    this.currentData = null;
    this.deltaData = null;
    this.hitNodes = [];
    this.rotation = -0.4;
    this.tilt = -0.28;
    this.lastTimestamp = 0;
  }

  async init() {
    this.mount();
    try {
      const [mapDocument, deltaDocument] = await Promise.all([
        fetch(this.mapUrl, { credentials: 'same-origin' }).then((response) => response.ok ? response.json() : Promise.reject(new Error(`Map request failed: ${response.status}`))),
        fetch(this.deltaUrl, { credentials: 'same-origin' }).then((response) => response.ok ? response.json() : null),
      ]);
      this.currentData = mapDocument;
      this.deltaData = deltaDocument;
      this.state.mode = this.resolveMode(this.state.mode, mapDocument.modes);
      this.root.dataset.currentMode = this.state.mode;
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
        this.statusLine.textContent = 'Globe fallback engaged. Web surface is using the bounded tactical backup below.';
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
      <div class="black-ledger-geoscape__shell">
        <div class="black-ledger-geoscape__stage">
          <canvas class="black-ledger-geoscape__canvas" role="img" aria-label="Black Ledger geoscape globe"></canvas>
          <div class="black-ledger-geoscape__overlay">
            <div class="black-ledger-geoscape__eyebrow">Black Ledger geoscape</div>
            <div class="black-ledger-geoscape__headline">${this.variant === 'teaser' ? 'Turn 1 already ran.' : 'Turn 1 pressure live.'}</div>
            <div class="black-ledger-geoscape__status"></div>
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
          <button type="button" class="black-ledger-geoscape__replay button-like button-like--secondary">Replay Turn 1</button>
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
    this.canvas.height = Math.max(240, Math.floor(bounds.height * ratio));
    this.canvas.style.width = `${Math.max(320, Math.floor(bounds.width))}px`;
    this.canvas.style.height = `${Math.max(240, Math.floor(bounds.height))}px`;
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
        : 200 + index * 140;
      const centerY = regions.length > 0
        ? regions.reduce((sum, region) => sum + region.centerY, 0) / regions.length
        : 180 + (index % 2) * 180;
      return {
        ...faction,
        slug: slugify(faction.factionId),
        lat: yToLat(centerY),
        lon: xToLon(centerX),
        influenceRadius: clamp(0.32 + (regions.reduce((sum, region) => sum + region.influence, 0) / Math.max(1, regions.length)) / 210, 0.28, 0.72),
        regionCount: regions.length,
        heat: regions.reduce((sum, region) => sum + region.heat, 0),
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
      ? '<p class="muted-copy">Keyboard and reduced-motion safe faction chooser.</p>'
      : '<p class="muted-copy">Accessible fallback list for faction focus, hotspots, and replay state.</p>';
    const factionItems = this.factionNodes.map((faction) => `
      <li>
        <button type="button" class="black-ledger-geoscape__list-button" data-faction-select="${faction.slug}">
          <strong>${faction.name}</strong>
          <span>${faction.type} · ${faction.publicSummary}</span>
        </button>
      </li>`).join('');
    const eventItems = this.events.slice(0, 4).map((event) => `<li><strong>${event.title}</strong><span>${event.summary}</span></li>`).join('');
    this.fallbackList.innerHTML = `
      ${intro}
      <div class="black-ledger-geoscape__list-grid">
        <section>
          <h4>Factions</h4>
          <ul class="black-ledger-geoscape__list">${factionItems}</ul>
        </section>
        <section>
          <h4>Turn 1 hotspots</h4>
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
    this.updatePanel();
  }

  hitTest(event) {
    const bounds = this.canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    return this.hitNodes.find((node) => Math.hypot(node.x - x, node.y - y) <= node.radius + 8) || null;
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
      this.tilt = clamp(-((selected.lat * Math.PI) / 540), -0.5, 0.16);
    }
    this.root.dataset.selectedFaction = this.state.selectedFaction;
    this.updatePanel();
    this.renderFrame();
  }

  setMode(mode) {
    this.state.mode = mode;
    this.root.dataset.currentMode = mode;
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
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    }
    this.state.replayState = 'idle';
    this.root.dataset.replayState = 'idle';
    this.replayButton.textContent = 'Replay Turn 1';
    this.updatePanel();
  }

  updatePanel() {
    if (!this.panelTitle) {
      return;
    }

    const selectedFaction = this.factionNodes.find((item) => item.slug === (this.state.selectedFaction || this.state.hoveredFaction));
    const highlightedEvent = this.events[this.state.replayState === 'turn-0' ? 0 : clamp(this.state.replayIndex, 0, Math.max(0, this.events.length - 1))];
    const activeFaction = selectedFaction || this.factionNodes[0];
    const relatedRegions = this.currentData.regions.filter((region) => slugify(region.dominantFactionId) === activeFaction.slug);
    const dispatchHref = highlightedEvent?.dispatchHref || '/ledger/dispatches';
    const promoHref = `/ledger/factions/${activeFaction.slug}/promo`;

    if (this.state.replayState === 'turn-0') {
      this.panelTag.textContent = 'Turn 0 baseline';
      this.panelTitle.textContent = 'Before the first pressure spike';
      this.panelSummary.textContent = this.deltaData?.summary || 'Baseline district posture before Turn 1 hotspots and arcs materialize.';
    } else {
      this.panelTag.textContent = activeFaction.type || 'Faction pressure';
      this.panelTitle.textContent = activeFaction.name;
      this.panelSummary.textContent = activeFaction.publicSummary;
    }

    const metrics = [
      `Mode: ${this.state.mode.replace('-', ' ')}`,
      `Districts: ${relatedRegions.length}`,
      `Heat: ${Math.max(0, activeFaction.heat || 0)}`,
      highlightedEvent?.sourceReceiptId ? `Receipt: ${highlightedEvent.sourceReceiptId}` : `Turn: ${this.currentData.currentTurn}`,
    ];
    this.panelMetrics.innerHTML = metrics.map((metric) => `<span>${metric}</span>`).join('');

    const primaryHref = this.variant === 'onboarding'
      ? `#faction-join-${activeFaction.slug}`
      : `/ledger/factions/${activeFaction.slug}`;
    const primaryLabel = this.variant === 'onboarding' ? 'Join this faction' : 'Open faction file';
    const secondaryHref = this.variant === 'onboarding'
      ? '/account/ledger/onboarding?step=choose-path'
      : promoHref;
    const secondaryLabel = this.variant === 'onboarding' ? 'Found my own' : 'Open storyboard';
    this.panelActions.innerHTML = `
      <a class="button-like button-like--primary" href="${primaryHref}">${primaryLabel}</a>
      <a class="button-like button-like--secondary" href="${secondaryHref}">${secondaryLabel}</a>
      <a class="inline-link" href="${dispatchHref}">Latest dispatch</a>
    `;

    if (this.statusLine) {
      this.statusLine.textContent = this.reducedMotion
        ? 'Reduced motion active. Replay advances step by step.'
        : `Mode ${this.state.mode.replace('-', ' ')} · ${this.state.replayState === 'idle' ? 'idle geoscape' : this.root.dataset.replayState}`;
    }
    this.root.dataset.renderSignature = `${this.state.mode}:${activeFaction.slug}:${this.root.dataset.replayState || 'idle'}`;
  }

  startLoop() {
    const tick = (timestamp) => {
      const deltaSeconds = this.lastTimestamp === 0 ? 0 : (timestamp - this.lastTimestamp) / 1000;
      this.lastTimestamp = timestamp;
      if (!this.reducedMotion && this.state.replayState !== 'playing') {
        this.rotation += deltaSeconds * 0.1;
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
    const radius = Math.min(width, height) * (this.variant === 'teaser' ? 0.28 : 0.3);
    ctx.clearRect(0, 0, width, height);

    const background = ctx.createRadialGradient(centerX * 0.85, centerY * 0.7, radius * 0.15, centerX, centerY, radius * 1.9);
    background.addColorStop(0, 'rgba(32, 58, 83, 0.32)');
    background.addColorStop(0.55, 'rgba(8, 17, 28, 0.74)');
    background.addColorStop(1, 'rgba(3, 7, 12, 0.98)');
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(centerX, centerY);
    this.drawSphere(ctx, radius, time);
    this.drawArcs(ctx, radius, time);
    this.drawFactions(ctx, radius, time);
    this.drawEvents(ctx, radius, time);
    ctx.restore();
  }

  drawSphere(ctx, radius, time) {
    const body = ctx.createRadialGradient(-radius * 0.35, -radius * 0.45, radius * 0.1, 0, 0, radius * 1.15);
    body.addColorStop(0, 'rgba(33, 66, 99, 0.96)');
    body.addColorStop(0.55, 'rgba(13, 28, 43, 0.98)');
    body.addColorStop(1, 'rgba(6, 13, 20, 1)');
    ctx.fillStyle = body;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, TWO_PI);
    ctx.fill();

    ctx.strokeStyle = 'rgba(104, 219, 255, 0.12)';
    ctx.lineWidth = 1;
    for (let i = 1; i <= 5; i += 1) {
      ctx.beginPath();
      ctx.ellipse(0, 0, radius, radius * Math.cos((i / 6) * (Math.PI / 2)), 0, 0, TWO_PI);
      ctx.stroke();
    }
    for (let i = 0; i < 8; i += 1) {
      ctx.save();
      ctx.rotate((i / 8) * Math.PI);
      ctx.beginPath();
      ctx.moveTo(0, -radius);
      ctx.quadraticCurveTo(radius * 0.22, 0, 0, radius);
      ctx.stroke();
      ctx.restore();
    }

    ctx.strokeStyle = 'rgba(92, 226, 255, 0.28)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, 0, radius + 12, 0, TWO_PI);
    ctx.stroke();

    if (!this.reducedMotion) {
      ctx.strokeStyle = 'rgba(92, 226, 255, 0.1)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(0, 0, radius + 22 + Math.sin(time * 1.3) * 4, 0, TWO_PI);
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
      visible: rotated.z > -radius * 0.2,
    };
  }

  drawFactions(ctx, radius, time) {
    this.hitNodes = [];
    this.factionNodes.forEach((faction, index) => {
      const projected = this.project(faction.lat, faction.lon, radius * 0.92);
      if (!projected.visible) {
        return;
      }

      const selected = faction.slug === this.state.selectedFaction;
      const hovered = faction.slug === this.state.hoveredFaction;
      const pulse = this.reducedMotion ? 1 : (1 + Math.sin(time * 1.6 + index) * 0.08);
      const haloRadius = radius * faction.influenceRadius * (selected ? 0.4 : 0.26) * pulse;
      ctx.fillStyle = hexToRgba(faction.colorPrimary, selected ? 0.26 : hovered ? 0.2 : 0.14);
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, haloRadius, 0, TWO_PI);
      ctx.fill();

      ctx.fillStyle = hexToRgba(faction.colorPrimary, 0.98);
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, selected ? 8 : 6, 0, TWO_PI);
      ctx.fill();
      ctx.strokeStyle = hexToRgba(faction.colorSecondary || faction.colorPrimary, 0.95);
      ctx.lineWidth = selected ? 3 : 2;
      ctx.beginPath();
      ctx.arc(projected.x, projected.y, selected ? 13 : 10, 0, TWO_PI);
      ctx.stroke();

      ctx.fillStyle = 'rgba(226, 237, 248, 0.92)';
      ctx.font = selected ? '700 13px ui-monospace, monospace' : '600 11px ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(faction.name, projected.x, projected.y - haloRadius - 10);
      this.hitNodes.push({ slug: faction.slug, x: projected.x + this.canvas.clientWidth / 2, y: projected.y + this.canvas.clientHeight / 2, radius: 14 });
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

      const projected = this.project(event.lat, event.lon, radius * 0.98);
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

      const pulse = this.reducedMotion ? 1 : (1 + Math.sin(time * 2.4 + index) * 0.16);
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
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
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

      const source = this.project(arc.source.lat, arc.source.lon, radius * 0.96);
      const target = this.project(arc.target.lat, arc.target.lon, radius * 0.96);
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
      ctx.globalAlpha = this.state.mode === 'influence' || this.state.mode === 'recent-changes' || this.state.mode === arcMode ? 1 : 0.24;

      const midpointX = (source.x + target.x) / 2;
      const midpointY = (source.y + target.y) / 2 - clamp(18 + arc.intensity * 0.32, 26, 54);
      ctx.strokeStyle = arc.arcType === 'magic'
        ? 'rgba(172, 126, 255, 0.8)'
        : arc.arcType === 'logistics'
          ? 'rgba(89, 244, 186, 0.78)'
          : arc.arcType === 'intel'
            ? 'rgba(210, 225, 241, 0.74)'
            : arc.arcType === 'conflict'
              ? 'rgba(255, 89, 114, 0.82)'
              : 'rgba(255, 164, 88, 0.82)';
      ctx.lineWidth = 1.5 + arc.intensity / 36;
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.quadraticCurveTo(midpointX, midpointY, target.x, target.y);
      ctx.stroke();

      if (!this.reducedMotion) {
        const travel = (time * 0.22 + index * 0.13) % 1;
        const t = travel;
        const x = (1 - t) * (1 - t) * source.x + 2 * (1 - t) * t * midpointX + t * t * target.x;
        const y = (1 - t) * (1 - t) * source.y + 2 * (1 - t) * t * midpointY + t * t * target.y;
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.beginPath();
        ctx.arc(x, y, 2.8, 0, TWO_PI);
        ctx.fill();
      }
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

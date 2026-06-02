const GLOBE_WORLD_ID = 'emerald-sprawl-prelude';
const BASE_MAP_WIDTH = 1200;
const BASE_MAP_HEIGHT = 760;
const TWO_PI = Math.PI * 2;
const VIDEO_GLOBE_IDLE_SECONDS = 14;
const IS_AUTOMATED_QA = Boolean(navigator.webdriver);
const EARTH_LANDMASSES = [
  { id: 'north-america', fill: ['#315f49', '#7fb06a'], coastline: '#c9e5c1', points: [{ lat: 12, lon: -116 }, { lat: 20, lon: -104 }, { lat: 28, lon: -98 }, { lat: 36, lon: -104 }, { lat: 45, lon: -110 }, { lat: 56, lon: -122 }, { lat: 67, lon: -148 }, { lat: 72, lon: -160 }, { lat: 69, lon: -126 }, { lat: 62, lon: -108 }, { lat: 54, lon: -90 }, { lat: 50, lon: -74 }, { lat: 45, lon: -66 }, { lat: 34, lon: -78 }, { lat: 25, lon: -83 }, { lat: 19, lon: -90 }] },
  { id: 'greenland', fill: ['#8aa385', '#d5e1d1'], coastline: '#f2fbf0', points: [{ lat: 60, lon: -52 }, { lat: 66, lon: -48 }, { lat: 72, lon: -42 }, { lat: 79, lon: -34 }, { lat: 82, lon: -24 }, { lat: 77, lon: -18 }, { lat: 70, lon: -24 }, { lat: 63, lon: -40 }] },
  { id: 'south-america', fill: ['#336a43', '#7cbc67'], coastline: '#cae8c6', points: [{ lat: 12, lon: -80 }, { lat: 10, lon: -72 }, { lat: 6, lon: -62 }, { lat: -5, lon: -54 }, { lat: -15, lon: -51 }, { lat: -24, lon: -55 }, { lat: -35, lon: -60 }, { lat: -46, lon: -68 }, { lat: -53, lon: -74 }, { lat: -50, lon: -67 }, { lat: -35, lon: -72 }, { lat: -18, lon: -78 }, { lat: -3, lon: -81 }] },
  { id: 'africa', fill: ['#586f3e', '#b89b58'], coastline: '#f0dbaf', points: [{ lat: 35, lon: -16 }, { lat: 30, lon: -3 }, { lat: 25, lon: 12 }, { lat: 12, lon: 24 }, { lat: 2, lon: 33 }, { lat: -8, lon: 40 }, { lat: -18, lon: 34 }, { lat: -28, lon: 28 }, { lat: -34, lon: 18 }, { lat: -30, lon: 8 }, { lat: -18, lon: 2 }, { lat: -6, lon: -4 }, { lat: 8, lon: -10 }, { lat: 21, lon: -16 }] },
  { id: 'eurasia', fill: ['#4e6e4a', '#92b16f'], coastline: '#d8efc8', points: [{ lat: 37, lon: -10 }, { lat: 44, lon: -2 }, { lat: 50, lon: 10 }, { lat: 56, lon: 28 }, { lat: 60, lon: 48 }, { lat: 64, lon: 74 }, { lat: 68, lon: 98 }, { lat: 68, lon: 126 }, { lat: 61, lon: 150 }, { lat: 54, lon: 160 }, { lat: 46, lon: 146 }, { lat: 34, lon: 130 }, { lat: 24, lon: 118 }, { lat: 16, lon: 104 }, { lat: 12, lon: 86 }, { lat: 18, lon: 70 }, { lat: 28, lon: 58 }, { lat: 35, lon: 44 }, { lat: 40, lon: 30 }, { lat: 42, lon: 18 }, { lat: 39, lon: 6 }, { lat: 36, lon: -2 }] },
  { id: 'arabia-india', fill: ['#6f7542', '#d3a95d'], coastline: '#f0dcb1', points: [{ lat: 30, lon: 34 }, { lat: 26, lon: 44 }, { lat: 18, lon: 56 }, { lat: 12, lon: 64 }, { lat: 8, lon: 76 }, { lat: 16, lon: 82 }, { lat: 24, lon: 74 }, { lat: 28, lon: 62 }, { lat: 30, lon: 50 }] },
  { id: 'australia', fill: ['#5d7048', '#b79d66'], coastline: '#efdcb4', points: [{ lat: -12, lon: 113 }, { lat: -16, lon: 126 }, { lat: -24, lon: 138 }, { lat: -32, lon: 151 }, { lat: -40, lon: 147 }, { lat: -42, lon: 133 }, { lat: -34, lon: 118 }, { lat: -24, lon: 113 }] },
  { id: 'antarctica', fill: ['#b8cad3', '#eef7ff'], coastline: '#f8fdff', points: [{ lat: -70, lon: -180 }, { lat: -74, lon: -132 }, { lat: -76, lon: -86 }, { lat: -74, lon: -32 }, { lat: -75, lon: 20 }, { lat: -78, lon: 76 }, { lat: -76, lon: 126 }, { lat: -72, lon: 172 }, { lat: -68, lon: 180 }] },
];
const EARTH_MOUNTAIN_RANGES = [
  { id: 'rockies', color: '#e7dfc7', points: [{ lat: 58, lon: -140 }, { lat: 50, lon: -128 }, { lat: 42, lon: -118 }, { lat: 34, lon: -108 }, { lat: 24, lon: -100 }] },
  { id: 'andes', color: '#e8dfcb', points: [{ lat: 9, lon: -78 }, { lat: -4, lon: -76 }, { lat: -18, lon: -72 }, { lat: -32, lon: -70 }, { lat: -48, lon: -72 }] },
  { id: 'alps-atlas', color: '#efe4cf', points: [{ lat: 35, lon: -8 }, { lat: 36, lon: 6 }, { lat: 44, lon: 12 }, { lat: 47, lon: 18 }] },
  { id: 'east-africa', color: '#dfd6be', points: [{ lat: 14, lon: 36 }, { lat: 8, lon: 38 }, { lat: -2, lon: 35 }, { lat: -14, lon: 31 }] },
  { id: 'urals', color: '#e6dfc9', points: [{ lat: 63, lon: 54 }, { lat: 56, lon: 58 }, { lat: 49, lon: 60 }] },
  { id: 'himalaya', color: '#f2ead8', points: [{ lat: 32, lon: 72 }, { lat: 31, lon: 82 }, { lat: 30, lon: 92 }, { lat: 28, lon: 102 }] },
  { id: 'great-dividing', color: '#e9dcc2', points: [{ lat: -17, lon: 146 }, { lat: -24, lon: 149 }, { lat: -31, lon: 151 }, { lat: -37, lon: 149 }] },
];
const EARTH_CLOUD_BANDS = [
  { lat: 14, startLon: -165, endLon: -20, width: 12, alpha: 0.18, drift: 0.45 },
  { lat: -8, startLon: 24, endLon: 176, width: 14, alpha: 0.14, drift: -0.38 },
  { lat: 42, startLon: -72, endLon: 132, width: 10, alpha: 0.1, drift: 0.28 },
];

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
    this.videoMp4Url = root.dataset.globeVideoMp4 || '/media/ledger/globe/black-ledger-video-globe-idle.mp4';
    this.videoWebmUrl = root.dataset.globeVideoWebm || '/media/ledger/globe/black-ledger-video-globe-idle.webm';
    this.videoPosterUrl = root.dataset.globeVideoPoster || '/media/ledger/globe/black-ledger-video-globe-idle-poster.png';
    this.selectedFactionSlug = slugify(root.dataset.selectedFaction || '');
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.disableWebGl = root.dataset.disableWebgl === 'true' || IS_AUTOMATED_QA;
    this.disableAmbientVideo = root.dataset.disableAmbientVideo === 'true' || IS_AUTOMATED_QA;
    this.state = {
      mode: root.dataset.initialMode || 'influence',
      hoveredFaction: '',
      selectedFaction: this.selectedFactionSlug,
      replayState: 'idle',
      replayIndex: 0,
      tickHeadline: root.dataset.tickHeadline || 'Turn 1 pressure live.',
    };
    this.frame = null;
    this.glCanvas = null;
    this.gl = null;
    this.glProgram = null;
    this.glBuffer = null;
    this.glTexture = null;
    this.glUniforms = null;
    this.videoPlate = null;
    this.videoPlateReady = false;
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
    this.signalPrimary = null;
    this.signalSecondary = null;
    this.signalTertiary = null;
    this.modeButtons = [];
    this.replayButton = null;
    this.regionMap = new Map();
    this.factionNodes = [];
    this.regionShapesByFaction = new Map();
    this.events = [];
    this.arcs = [];
    this.currentData = null;
    this.deltaData = null;
    this.hitNodes = [];
    this.rotation = -0.52;
    this.tilt = -0.2;
    this.lastTimestamp = 0;
    this.handleResize = () => this.syncCanvasSize();
    this.handleWebGlContextLost = (event) => {
      event.preventDefault();
      this.gl = null;
      this.glProgram = null;
      this.glBuffer = null;
      this.glTexture = null;
      this.glUniforms = null;
      this.root.dataset.renderer = 'canvas-geoscape';
      this.renderFrame();
    };
    this.handleWebGlContextRestored = () => {
      this.initWebGl();
      this.renderFrame();
    };
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
    if (IS_AUTOMATED_QA) {
      this.root.dataset.qaRenderer = 'canvas-only';
    }
    this.root.innerHTML = `
      <div class="black-ledger-geoscape__shell black-ledger-geoscape__shell--${this.variant}">
        <div class="black-ledger-geoscape__stage">
          <div class="black-ledger-geoscape__stage-skin" aria-hidden="true"></div>
          <video class="black-ledger-geoscape__video-plate" aria-hidden="true" muted playsinline loop preload="${this.disableAmbientVideo ? 'none' : 'metadata'}" poster="${this.videoPosterUrl}">
            <source src="${this.videoWebmUrl}" type="video/webm">
            <source src="${this.videoMp4Url}" type="video/mp4">
          </video>
          <canvas class="black-ledger-geoscape__webgl" aria-hidden="true"></canvas>
          <canvas class="black-ledger-geoscape__canvas" role="img" aria-label="Black Ledger command globe"></canvas>
          <div class="black-ledger-geoscape__signal-rail" aria-hidden="true">
            <span class="black-ledger-geoscape__signal-chip black-ledger-geoscape__signal-chip--primary">district pressure live</span>
            <span class="black-ledger-geoscape__signal-chip black-ledger-geoscape__signal-chip--secondary">runner fallout tracked</span>
            <span class="black-ledger-geoscape__signal-chip black-ledger-geoscape__signal-chip--tertiary">newsroom feed armed</span>
          </div>
          <div class="black-ledger-geoscape__overlay">
            <div class="black-ledger-geoscape__eyebrow">Black Ledger overlay</div>
            <div class="black-ledger-geoscape__headline">${this.variant === 'teaser' ? 'The city remembers.' : 'Heat is moving.'}</div>
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

    this.videoPlate = this.root.querySelector('.black-ledger-geoscape__video-plate');
    this.glCanvas = this.root.querySelector('.black-ledger-geoscape__webgl');
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
    this.signalPrimary = this.root.querySelector('.black-ledger-geoscape__signal-chip--primary');
    this.signalSecondary = this.root.querySelector('.black-ledger-geoscape__signal-chip--secondary');
    this.signalTertiary = this.root.querySelector('.black-ledger-geoscape__signal-chip--tertiary');
    this.replayButton = this.root.querySelector('.black-ledger-geoscape__replay');
    if (this.videoPlate && !this.disableAmbientVideo) {
      this.root.dataset.videoGlobe = 'loading';
      const markVideoReady = () => {
        this.videoPlateReady = true;
        this.root.dataset.videoGlobe = 'ready';
        this.root.dataset.videoLayer = 'ambient';
        if (this.reducedMotion) {
          this.videoPlate.pause();
        } else {
          this.videoPlate.play?.().catch(() => {});
        }
        this.renderFrame();
      };
      const markVideoFallback = () => {
        this.videoPlateReady = false;
        this.root.dataset.videoGlobe = 'fallback';
        this.renderFrame();
      };
      this.videoPlate.addEventListener('canplay', markVideoReady, { once: true });
      this.videoPlate.addEventListener('loadeddata', markVideoReady, { once: true });
      this.videoPlate.addEventListener('error', markVideoFallback, { once: true });
      if (this.reducedMotion) {
        this.videoPlate.pause();
      }
    } else if (this.videoPlate) {
      this.root.dataset.videoGlobe = 'disabled';
      this.root.dataset.videoLayer = 'canvas-only';
    }
    this.glCanvas?.addEventListener('webglcontextlost', this.handleWebGlContextLost, false);
    this.glCanvas?.addEventListener('webglcontextrestored', this.handleWebGlContextRestored, false);
    this.initWebGl();
    this.syncCanvasSize();
    window.addEventListener('resize', this.handleResize, { passive: true });
  }

  syncCanvasSize() {
    if (!this.canvas) {
      return;
    }

    const stage = this.root.querySelector('.black-ledger-geoscape__stage');
    const bounds = stage.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (this.glCanvas) {
      this.glCanvas.width = Math.max(320, Math.floor(bounds.width * ratio));
      this.glCanvas.height = Math.max(300, Math.floor(bounds.height * ratio));
      this.glCanvas.style.width = `${Math.max(320, Math.floor(bounds.width))}px`;
      this.glCanvas.style.height = `${Math.max(300, Math.floor(bounds.height))}px`;
    }
    this.canvas.width = Math.max(320, Math.floor(bounds.width * ratio));
    this.canvas.height = Math.max(300, Math.floor(bounds.height * ratio));
    this.canvas.style.width = `${Math.max(320, Math.floor(bounds.width))}px`;
    this.canvas.style.height = `${Math.max(300, Math.floor(bounds.height))}px`;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(ratio, ratio);
    this.renderFrame();
  }

  initWebGl() {
    if (this.disableWebGl) {
      this.root.dataset.renderer = 'canvas-geoscape';
      return;
    }
    if (!this.glCanvas) {
      return;
    }
    const gl = this.glCanvas.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: true });
    if (!gl) {
      return;
    }

    const vertexSource = `
      attribute vec2 a_position;
      varying vec2 v_uv;
      void main() {
        v_uv = a_position * 0.5 + 0.5;
        gl_Position = vec4(a_position, 0.0, 1.0);
      }
    `;
    const fragmentSource = `
      precision mediump float;
      varying vec2 v_uv;
      uniform vec2 u_resolution;
      uniform float u_time;
      uniform float u_radius;
      uniform float u_yaw;
      uniform float u_pitch;
      uniform sampler2D u_earth;

      vec3 rotateYawPitch(vec3 point, float yaw, float pitch) {
        float sinYaw = sin(yaw);
        float cosYaw = cos(yaw);
        float sinPitch = sin(pitch);
        float cosPitch = cos(pitch);
        vec3 yawed = vec3(
          point.x * cosYaw - point.z * sinYaw,
          point.y,
          point.x * sinYaw + point.z * cosYaw
        );
        return vec3(
          yawed.x,
          yawed.y * cosPitch - yawed.z * sinPitch,
          yawed.y * sinPitch + yawed.z * cosPitch
        );
      }

      void main() {
        vec2 frag = gl_FragCoord.xy;
        vec2 center = u_resolution * 0.5;
        vec2 delta = frag - center;
        float dist = length(delta);

        vec3 color = vec3(0.006, 0.017, 0.026);
        float starNoise = fract(sin(dot(frag + vec2(u_time * 11.0, u_time * 7.0), vec2(12.9898, 78.233))) * 43758.5453);
        float star = step(0.9984, starNoise) * (0.3 + 0.7 * fract(starNoise * 91.0));
        color += vec3(star * 0.85);
        float halo = smoothstep(u_radius * 1.9, u_radius * 0.2, dist);
        color += vec3(0.01, 0.08, 0.1) * halo;
        float alpha = clamp(0.18 + halo * 0.5, 0.18, 0.78);

        if (dist <= u_radius) {
          vec2 sphere = delta / u_radius;
          float z = sqrt(max(0.0, 1.0 - dot(sphere, sphere)));
          vec3 normal = normalize(rotateYawPitch(vec3(sphere.x, -sphere.y, z), u_yaw, u_pitch));
          float lat = degrees(asin(clamp(normal.y, -1.0, 1.0)));
          float lon = degrees(atan(normal.x, normal.z));
          vec2 mapUv = vec2((lon + 180.0) / 360.0, (90.0 - lat) / 180.0);
          vec3 tex = texture2D(u_earth, mapUv).rgb;

          vec3 lightDir = normalize(vec3(-0.55, 0.35, 0.76));
          float diffuse = max(dot(normal, lightDir), 0.0);
          float rim = pow(1.0 - max(normal.z, 0.0), 2.0);
          float specular = pow(max(dot(reflect(-lightDir, normal), vec3(0.0, 0.0, 1.0)), 0.0), 22.0);
          vec3 lit = tex * (0.26 + diffuse * 0.92) + vec3(0.08, 0.47, 0.46) * rim * 0.58 + vec3(0.98, 0.66, 0.22) * specular * 0.12;
          float atmosphere = smoothstep(0.7, 1.0, 1.0 - z);
          color = lit + vec3(0.12, 0.64, 0.67) * atmosphere * 0.18;
          alpha = 1.0;
        } else if (dist <= u_radius * 1.08) {
          float edge = 1.0 - smoothstep(u_radius, u_radius * 1.08, dist);
          color += vec3(0.08, 0.72, 0.78) * edge * 0.34;
          alpha = max(alpha, edge * 0.62);
        }

        gl_FragColor = vec4(color, alpha);
      }
    `;

    const vertexShader = this.compileGlShader(gl, gl.VERTEX_SHADER, vertexSource);
    const fragmentShader = this.compileGlShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
    if (!vertexShader || !fragmentShader) {
      return;
    }
    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error(gl.getProgramInfoLog(program));
      return;
    }

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );

    this.gl = gl;
    this.glProgram = program;
    this.glBuffer = buffer;
    this.glUniforms = {
      position: gl.getAttribLocation(program, 'a_position'),
      resolution: gl.getUniformLocation(program, 'u_resolution'),
      time: gl.getUniformLocation(program, 'u_time'),
      radius: gl.getUniformLocation(program, 'u_radius'),
      yaw: gl.getUniformLocation(program, 'u_yaw'),
      pitch: gl.getUniformLocation(program, 'u_pitch'),
      earth: gl.getUniformLocation(program, 'u_earth'),
    };
    this.glTexture = this.createEarthTexture(gl);
    this.root.dataset.renderer = 'webgl-geoscape';
  }

  compileGlShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(shader));
      return null;
    }
    return shader;
  }

  createEarthTexture(gl) {
    const textureCanvas = document.createElement('canvas');
    textureCanvas.width = 2048;
    textureCanvas.height = 1024;
    const ctx = textureCanvas.getContext('2d');

    const ocean = ctx.createLinearGradient(0, 0, 0, textureCanvas.height);
    ocean.addColorStop(0, '#14505f');
    ocean.addColorStop(0.45, '#0a293c');
    ocean.addColorStop(1, '#030914');
    ctx.fillStyle = ocean;
    ctx.fillRect(0, 0, textureCanvas.width, textureCanvas.height);

    const drawMapPath = (points) => {
      ctx.beginPath();
      points.forEach((point, index) => {
        const x = ((point.lon + 180) / 360) * textureCanvas.width;
        const y = ((90 - point.lat) / 180) * textureCanvas.height;
        if (index === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.closePath();
    };

    EARTH_LANDMASSES.forEach((landmass) => {
      const xs = landmass.points.map((point) => ((point.lon + 180) / 360) * textureCanvas.width);
      const ys = landmass.points.map((point) => ((90 - point.lat) / 180) * textureCanvas.height);
      const fill = ctx.createLinearGradient(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys));
      fill.addColorStop(0, landmass.fill[0]);
      fill.addColorStop(0.55, landmass.fill[1]);
      fill.addColorStop(1, '#24362d');
      drawMapPath(landmass.points);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = landmass.coastline;
      ctx.lineWidth = 3;
      ctx.stroke();
    });

    EARTH_MOUNTAIN_RANGES.forEach((range) => {
      ctx.beginPath();
      range.points.forEach((point, index) => {
        const x = ((point.lon + 180) / 360) * textureCanvas.width;
        const y = ((90 - point.lat) / 180) * textureCanvas.height;
        if (index === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.strokeStyle = 'rgba(90, 63, 38, 0.6)';
      ctx.lineWidth = 10;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.strokeStyle = range.color;
      ctx.lineWidth = 5;
      ctx.stroke();
    });

    EARTH_CLOUD_BANDS.forEach((band, index) => {
      ctx.fillStyle = `rgba(255,255,255,${band.alpha})`;
      ctx.beginPath();
      for (let step = 0; step <= 48; step += 1) {
        const ratio = step / 48;
        const lon = band.startLon + ((band.endLon - band.startLon) * ratio);
        const lat = band.lat + Math.sin((ratio * Math.PI * 4) + index) * 3.5;
        const x = ((lon + 180) / 360) * textureCanvas.width;
        const y = ((90 - lat) / 180) * textureCanvas.height;
        const width = (textureCanvas.height * 0.008) * band.width * (0.7 + Math.sin(ratio * Math.PI * 2) * 0.15);
        if (step === 0) {
          ctx.moveTo(x, y - width);
        } else {
          ctx.lineTo(x, y - width);
        }
      }
      for (let step = 48; step >= 0; step -= 1) {
        const ratio = step / 48;
        const lon = band.startLon + ((band.endLon - band.startLon) * ratio);
        const lat = band.lat + Math.sin((ratio * Math.PI * 4) + index) * 3.5;
        const x = ((lon + 180) / 360) * textureCanvas.width;
        const y = ((90 - lat) / 180) * textureCanvas.height;
        const width = (textureCanvas.height * 0.008) * band.width * (0.7 + Math.sin(ratio * Math.PI * 2) * 0.15);
        ctx.lineTo(x, y + width);
      }
      ctx.closePath();
      ctx.fill();
    });

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, textureCanvas);
    return texture;
  }

  renderWebGlBase(time, width, height, radius) {
    if (!this.gl || !this.glProgram || !this.glBuffer || !this.glTexture) {
      return false;
    }
    const gl = this.gl;
    const drawingWidth = this.glCanvas.width || gl.drawingBufferWidth;
    const drawingHeight = this.glCanvas.height || gl.drawingBufferHeight;
    const pixelRatio = width > 0 ? drawingWidth / width : 1;
    gl.viewport(0, 0, drawingWidth, drawingHeight);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.glProgram);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.glBuffer);
    gl.enableVertexAttribArray(this.glUniforms.position);
    gl.vertexAttribPointer(this.glUniforms.position, 2, gl.FLOAT, false, 0, 0);
    gl.uniform2f(this.glUniforms.resolution, drawingWidth, drawingHeight);
    gl.uniform1f(this.glUniforms.time, time);
    gl.uniform1f(this.glUniforms.radius, radius * pixelRatio);
    gl.uniform1f(this.glUniforms.yaw, this.rotation);
    gl.uniform1f(this.glUniforms.pitch, this.tilt);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.glTexture);
    gl.uniform1i(this.glUniforms.earth, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    return true;
  }

  buildModel() {
    const data = this.currentData;
    const regionById = new Map();
    data.regions.forEach((region) => {
      const lat = yToLat(region.centerY);
      const lon = xToLon(region.centerX);
      regionById.set(region.regionId, {
        ...region,
        lat,
        lon,
        slug: slugify(region.regionId),
        polygon: this.parseRegionPolygon(region.polygonPoints),
      });
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
        countryShapes: regions
          .map((region) => regionById.get(region.regionId)?.polygon)
          .filter((polygon) => Array.isArray(polygon) && polygon.length >= 3),
      };
    });
    this.regionShapesByFaction = new Map(this.factionNodes.map((faction) => [faction.slug, faction.countryShapes || []]));

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

  parseRegionPolygon(polygonPoints) {
    return String(polygonPoints || '')
      .trim()
      .split(/\s+/)
      .map((point) => {
        const [xValue, yValue] = point.split(',');
        const x = Number.parseFloat(xValue);
        const y = Number.parseFloat(yValue);
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          return null;
        }

        return {
          lat: yToLat(y),
          lon: xToLon(x),
        };
      })
      .filter(Boolean);
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
      highlightedEvent?.sourceReceiptId && this.variant !== 'teaser' ? `Receipt: ${highlightedEvent.sourceReceiptId}` : `Turn: ${this.currentData.currentTurn}`,
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
    if (this.signalPrimary && this.signalSecondary && this.signalTertiary) {
      const eventTone = highlightedEvent?.eventType || 'recent-changes';
      const shortTitle = highlightedEvent?.title || activeFaction.name;
      this.root.dataset.signalTone = eventTone;
      this.signalPrimary.textContent = `${shortTitle.slice(0, 28)}${shortTitle.length > 28 ? '…' : ''}`;
      this.signalSecondary.textContent = `heat ${Math.max(0, activeFaction.heat)} · pressure ${activeFaction.pressureScore} · ${Math.max(1, relatedRegions.length)} districts`;
      this.signalTertiary.textContent = `${(activeFaction.type || 'faction').toLowerCase()} · ${this.state.mode.replace('-', ' ')} lane`;
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
    const usedVideoGlobe = this.videoPlateReady && this.root.dataset.videoGlobe === 'ready';
    if (usedVideoGlobe && this.videoPlate && !this.reducedMotion && this.state.replayState !== 'playing') {
      const phase = (this.videoPlate.currentTime % VIDEO_GLOBE_IDLE_SECONDS) / VIDEO_GLOBE_IDLE_SECONDS;
      this.rotation = (-36 * Math.PI / 180) + phase * TWO_PI;
    }
    if (usedVideoGlobe && this.root.dataset.renderer !== 'webgl-geoscape') {
      this.root.dataset.videoLayer = 'ambient';
    }
    const usedWebGl = this.renderWebGlBase(time, width, height, radius);
    if (!usedWebGl) {
      if (!usedVideoGlobe) {
        this.drawBackdrop(ctx, width, height, centerX, centerY, radius, time);
      }
    }
    ctx.save();
    ctx.translate(centerX, centerY);
    if (!usedWebGl && !usedVideoGlobe) {
      this.drawSphere(ctx, radius, time);
    }
    this.drawArcs(ctx, radius, time);
    this.drawFactions(ctx, radius, time);
    this.drawEvents(ctx, radius, time);
    ctx.restore();
  }

  drawBackdrop(ctx, width, height, centerX, centerY, radius, time) {
    const gradient = ctx.createRadialGradient(centerX * 0.84, centerY * 0.54, radius * 0.18, centerX, centerY, radius * 2.1);
    gradient.addColorStop(0, 'rgba(17, 106, 121, 0.34)');
    gradient.addColorStop(0.48, 'rgba(7, 13, 24, 0.78)');
    gradient.addColorStop(1, 'rgba(2, 7, 12, 1)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    const alleyGlow = ctx.createLinearGradient(width * 0.08, height * 0.68, width * 0.92, height * 0.2);
    alleyGlow.addColorStop(0, 'rgba(255, 100, 46, 0.16)');
    alleyGlow.addColorStop(0.48, 'rgba(19, 212, 234, 0.12)');
    alleyGlow.addColorStop(1, 'rgba(4, 18, 26, 0)');
    ctx.fillStyle = alleyGlow;
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = 'rgba(90, 220, 244, 0.08)';
    ctx.lineWidth = 1;
    for (let index = 0; index < 18; index += 1) {
      const y = height * 0.06 + index * ((height * 0.88) / 18);
      ctx.beginPath();
      ctx.moveTo(width * 0.04, y);
      ctx.lineTo(width * 0.96, y + Math.sin(time * 0.16 + index * 0.35) * 6);
      ctx.stroke();
    }

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
    atmosphere.addColorStop(0, 'rgba(36, 179, 191, 0.98)');
    atmosphere.addColorStop(0.48, 'rgba(10, 72, 92, 0.99)');
    atmosphere.addColorStop(0.78, 'rgba(6, 22, 38, 1)');
    atmosphere.addColorStop(1, 'rgba(2, 8, 14, 1)');
    ctx.fillStyle = atmosphere;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, TWO_PI);
    ctx.fill();

    this.drawOceanRelief(ctx, radius, time);
    this.drawPolarCaps(ctx, radius);
    this.drawLandmasses(ctx, radius);
    this.drawMountainRanges(ctx, radius);
    this.drawCloudBands(ctx, radius, time);

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

    ctx.strokeStyle = 'rgba(92, 226, 255, 0.34)';
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

  drawOceanRelief(ctx, radius, time) {
    const glow = ctx.createRadialGradient(-radius * 0.42, -radius * 0.56, radius * 0.06, -radius * 0.12, -radius * 0.08, radius * 1.18);
    glow.addColorStop(0, 'rgba(166, 227, 255, 0.22)');
    glow.addColorStop(0.3, 'rgba(73, 153, 214, 0.14)');
    glow.addColorStop(1, 'rgba(4, 17, 27, 0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, TWO_PI);
    ctx.fill();

    ctx.save();
    ctx.beginPath();
    ctx.arc(0, 0, radius * 0.995, 0, TWO_PI);
    ctx.clip();
    for (let index = 0; index < 12; index += 1) {
      const bandRadius = radius * (0.62 + index * 0.035);
      const alpha = 0.022 + ((Math.sin(time * 0.22 + index * 0.9) + 1) * 0.008);
      ctx.strokeStyle = `rgba(142, 214, 255, ${alpha.toFixed(3)})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.ellipse(
        Math.sin(time * 0.08 + index) * radius * 0.05,
        Math.cos(time * 0.11 + index * 0.7) * radius * 0.03,
        bandRadius,
        radius * (0.1 + (index % 3) * 0.03),
        (index * 0.22) - 0.5,
        0,
        TWO_PI,
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  drawPolarCaps(ctx, radius) {
    [
      { lat: 76, alpha: 0.84, size: 0.19 },
      { lat: -72, alpha: 0.68, size: 0.17 },
    ].forEach((cap) => {
      const projected = this.project(cap.lat, 0, radius * 0.98);
      if (!projected.visible) {
        return;
      }
      const capRadius = radius * cap.size;
      const fill = ctx.createRadialGradient(projected.x - capRadius * 0.22, projected.y - capRadius * 0.34, 0, projected.x, projected.y, capRadius);
      fill.addColorStop(0, `rgba(250, 252, 255, ${cap.alpha})`);
      fill.addColorStop(0.7, `rgba(214, 232, 243, ${(cap.alpha * 0.78).toFixed(3)})`);
      fill.addColorStop(1, 'rgba(161, 194, 212, 0)');
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.ellipse(projected.x, projected.y, capRadius * 1.4, capRadius, 0, 0, TWO_PI);
      ctx.fill();
    });
  }

  drawLandmasses(ctx, radius) {
    EARTH_LANDMASSES.forEach((landmass) => {
      const projectedPoints = landmass.points
        .map((point) => this.project(point.lat, point.lon, radius * 0.965))
        .filter((point) => point.visible);
      if (projectedPoints.length < 3) {
        return;
      }
      const minX = Math.min(...projectedPoints.map((point) => point.x));
      const maxX = Math.max(...projectedPoints.map((point) => point.x));
      const minY = Math.min(...projectedPoints.map((point) => point.y));
      const maxY = Math.max(...projectedPoints.map((point) => point.y));
      const fill = ctx.createLinearGradient(minX, minY, maxX, maxY);
      fill.addColorStop(0, hexToRgba(landmass.fill[0], 0.92));
      fill.addColorStop(0.55, hexToRgba(landmass.fill[1], 0.84));
      fill.addColorStop(1, 'rgba(32, 61, 43, 0.72)');

      ctx.beginPath();
      projectedPoints.forEach((point, index) => {
        if (index === 0) {
          ctx.moveTo(point.x, point.y);
        } else {
          ctx.lineTo(point.x, point.y);
        }
      });
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = hexToRgba(landmass.coastline, 0.74);
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.strokeStyle = 'rgba(9, 30, 20, 0.28)';
      ctx.lineWidth = 3.2;
      ctx.stroke();
    });
  }

  drawMountainRanges(ctx, radius) {
    EARTH_MOUNTAIN_RANGES.forEach((range) => {
      const projectedPoints = range.points
        .map((point) => this.project(point.lat, point.lon, radius * 0.978))
        .filter((point) => point.visible);
      if (projectedPoints.length < 2) {
        return;
      }
      ctx.beginPath();
      projectedPoints.forEach((point, index) => {
        if (index === 0) {
          ctx.moveTo(point.x, point.y);
        } else {
          ctx.lineTo(point.x, point.y);
        }
      });
      ctx.strokeStyle = 'rgba(68, 52, 31, 0.36)';
      ctx.lineWidth = 4.4;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.strokeStyle = hexToRgba(range.color, 0.66);
      ctx.lineWidth = 2.1;
      ctx.stroke();
    });
  }

  drawCloudBands(ctx, radius, time) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(0, 0, radius * 0.998, 0, TWO_PI);
    ctx.clip();
    EARTH_CLOUD_BANDS.forEach((band, index) => {
      const steps = 24;
      const driftOffset = Math.sin(time * band.drift + index) * 8;
      ctx.beginPath();
      for (let step = 0; step <= steps; step += 1) {
        const ratio = step / steps;
        const lon = band.startLon + ((band.endLon - band.startLon) * ratio) + driftOffset;
        const lat = band.lat + Math.sin((ratio * Math.PI * 4) + (time * 0.08) + index) * 2.8;
        const projected = this.project(lat, lon, radius * 1.01);
        if (!projected.visible) {
          continue;
        }
        const localWidth = radius * 0.012 * band.width * (0.7 + (Math.sin(ratio * Math.PI * 3) * 0.2));
        if (step === 0) {
          ctx.moveTo(projected.x, projected.y - localWidth);
        } else {
          ctx.lineTo(projected.x, projected.y - localWidth);
        }
      }
      for (let step = steps; step >= 0; step -= 1) {
        const ratio = step / steps;
        const lon = band.startLon + ((band.endLon - band.startLon) * ratio) + driftOffset;
        const lat = band.lat + Math.sin((ratio * Math.PI * 4) + (time * 0.08) + index) * 2.8;
        const projected = this.project(lat, lon, radius * 1.01);
        if (!projected.visible) {
          continue;
        }
        const localWidth = radius * 0.012 * band.width * (0.7 + (Math.sin(ratio * Math.PI * 3) * 0.2));
        ctx.lineTo(projected.x, projected.y + localWidth);
      }
      ctx.closePath();
      ctx.fillStyle = `rgba(244, 250, 255, ${band.alpha})`;
      ctx.fill();
    });
    ctx.restore();
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

  drawFactionBlob(ctx, faction, projected, radius, time) {
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

  drawFactionCountry(ctx, faction, projected, radius, time) {
    const countryShapes = this.regionShapesByFaction.get(faction.slug) || [];
    let drewBorderedCountry = false;
    countryShapes.forEach((shape) => {
      const projectedPoints = shape
        .map((point) => this.project(point.lat, point.lon, radius * 0.92))
        .filter((point) => point.visible);
      if (projectedPoints.length < 3) {
        return;
      }

      const minX = Math.min(...projectedPoints.map((point) => point.x));
      const maxX = Math.max(...projectedPoints.map((point) => point.x));
      const minY = Math.min(...projectedPoints.map((point) => point.y));
      const maxY = Math.max(...projectedPoints.map((point) => point.y));
      const fill = ctx.createLinearGradient(minX, minY, maxX, maxY);
      fill.addColorStop(0, hexToRgba(faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.42 : 0.28));
      fill.addColorStop(1, hexToRgba(faction.colorSecondary || faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.22 : 0.14));

      ctx.beginPath();
      projectedPoints.forEach((point, index) => {
        if (index === 0) {
          ctx.moveTo(point.x, point.y);
        } else {
          ctx.lineTo(point.x, point.y);
        }
      });
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = hexToRgba(faction.colorPrimary, faction.slug === this.state.selectedFaction ? 0.96 : 0.76);
      ctx.lineWidth = faction.slug === this.state.selectedFaction ? 2.6 : 1.45;
      ctx.stroke();
      drewBorderedCountry = true;
    });

    if (!drewBorderedCountry) {
      this.drawFactionBlob(ctx, faction, projected, radius, time);
    }
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

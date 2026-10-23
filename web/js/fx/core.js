// =============================================================================
// The holographic AI core - Canvas 2D, additive light, spring-smoothed states.
//
// Layers (back to front): ambient glow, orbital guides, radar sweep,
// far-side particles, tick ring, arc ring with a travelling light pulse,
// dashed ring, bracket ring, energy segments, reactive waveform ring,
// emitted light pulses, plasma energy sphere, near-side particles, bloom.
//
// Every visual parameter is a spring toward the current state's preset, so
// idle -> listening -> processing -> speaking morph continuously instead of
// switching. Glow is faked with layered additive strokes plus one blurred
// quarter-resolution bloom pass (no per-shape shadowBlur, which is slow).
// =============================================================================
import { Spring } from './spring.js';

const TAU = Math.PI * 2;

// Per-state targets. Weights (idleW/listenW/speakW/thinkW) blend waveform styles.
const PRESETS = {
  loading:   { energy: 0.35, spin: 0.55, wave: 0.6, swarm: 0.45, sweep: 0.35, violet: 0.2,  idleW: 1, listenW: 0, speakW: 0, thinkW: 0.5 },
  idle:      { energy: 0.6,  spin: 0.3,  wave: 1,   swarm: 0.5,  sweep: 0,    violet: 0.08, idleW: 1, listenW: 0, speakW: 0, thinkW: 0 },
  listening: { energy: 1,    spin: 0.8,  wave: 1,   swarm: 0.85, sweep: 0,    violet: 0,    idleW: 0.2, listenW: 1, speakW: 0, thinkW: 0 },
  thinking:  { energy: 0.92, spin: 2.4,  wave: 1,   swarm: 1.9,  sweep: 1,    violet: 0.7,  idleW: 0, listenW: 0, speakW: 0, thinkW: 1 },
  speaking:  { energy: 1,    spin: 1.0,  wave: 1,   swarm: 1.1,  sweep: 0,    violet: 0.12, idleW: 0, listenW: 0, speakW: 1, thinkW: 0 },
  error:     { energy: 0.45, spin: 0.14, wave: 0.7, swarm: 0.28, sweep: 0,    violet: 0,    idleW: 1, listenW: 0, speakW: 0, thinkW: 0 },
};

const COLORS = {
  loading:   { base: [120, 170, 215], accent: [150, 140, 255] },
  idle:      { base: [72, 212, 255],  accent: [140, 180, 255] },
  listening: { base: [44, 228, 255],  accent: [140, 240, 255] },
  thinking:  { base: [104, 176, 255], accent: [150, 128, 255] },
  speaking:  { base: [62, 236, 236],  accent: [160, 250, 255] },
  error:     { base: [255, 176, 72],  accent: [255, 130, 110] },
};

const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a < 0 ? 0 : a > 1 ? 1 : a.toFixed(3)})`;
const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const WHITE = [255, 255, 255];

const PLANES = [
  { inc: 1.16, node: 0.4, drift: 0.035 },
  { inc: 1.34, node: 2.5, drift: -0.025 },
  { inc: 0.58, node: 4.3, drift: 0.02 },
];

export class CoreRenderer {
  constructor(canvas, { getLevel, onFrameRate } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.getLevel = getLevel || (() => 0);
    this.onFrameRate = onFrameRate;

    this.springs = {};
    for (const key of Object.keys(PRESETS.idle)) this.springs[key] = new Spring(PRESETS.loading[key], { stiffness: 26, damping: 9 });
    this.base = COLORS.loading.base.map((v) => new Spring(v, { stiffness: 18, damping: 8 }));
    this.accent = COLORS.loading.accent.map((v) => new Spring(v, { stiffness: 18, damping: 8 }));
    this.state = 'loading';

    this.t = 0;
    this.rot = { a: 0, b: 0, c: 0, d: 0, sweep: 0, pulse: 0 };
    this.level = 0;
    this.levelHist = new Float32Array(72);
    this.histTimer = 0;
    this.speech = { env: 0, target: 0.5, timer: 0 };
    this.pulses = [];
    this.pulseTimer = 0;
    this.boost = new Spring(0, { stiffness: 40, damping: 10 });

    this.quality = 'high';
    this.particles = this._makeParticles(true);
    this.bloom = document.createElement('canvas');
    this.bctx = this.bloom.getContext('2d');
    this.reduced = false;

    this._frameTimes = [];
    this._last = 0;
    this._raf = 0;

    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
  }

  // ---------------------------------------------------------------------------
  setState(state) {
    if (!PRESETS[state] || state === this.state) return;
    const prev = this.state;
    this.state = state;
    for (const [key, spring] of Object.entries(this.springs)) spring.target = PRESETS[state][key];
    COLORS[state].base.forEach((v, i) => { this.base[i].target = v; });
    COLORS[state].accent.forEach((v, i) => { this.accent[i].target = v; });
    if (prev !== 'loading') this.emitPulse(state === 'thinking' ? 0.9 : 0.6);
  }

  setReducedMotion(reduced) { this.reduced = reduced; }

  /** Ripple of light from the sphere (state changes, taps, speech peaks). */
  emitPulse(strength = 0.6) {
    if (this.pulses.length < 8) this.pulses.push({ p: 0, s: strength });
  }

  /** Brief energy surge - used when the user interacts with the core. */
  nudge() {
    this.boost.velocity += 6;
    this.emitPulse(1);
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width) return;
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.size = rect.width;
    this.canvas.width = Math.round(rect.width * this.dpr);
    this.canvas.height = Math.round(rect.height * this.dpr);
    this.bloom.width = Math.max(1, Math.round(this.canvas.width / 4));
    this.bloom.height = Math.max(1, Math.round(this.canvas.height / 4));
  }

  start() {
    if (this._raf) return;
    const loop = (now) => {
      this._raf = requestAnimationFrame(loop);
      const dt = this._last ? Math.min(0.05, (now - this._last) / 1000) : 1 / 60;
      this._last = now;
      if (!this.size) return;
      this._update(dt);
      this._draw();
      this._monitor(now);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._last = 0;
  }

  // ---------------------------------------------------------------------------
  /**
   * Particle streams: comets travelling along tilted orbital bands (a bright
   * head with a tapering tail of dots), plus a little slow ambient dust.
   */
  _makeParticles(dense) {
    const parts = [];
    const streams = dense ? 6 : 4;
    for (let s = 0; s < streams; s++) {
      const orbit = 0.5 + s * 0.1 + Math.random() * 0.03;
      const speed = (0.2 + Math.random() * 0.28) * (Math.random() < 0.7 ? 1 : -1);
      for (let c = 0; c < (dense ? 2 : 1); c++) {
        const head = Math.random() * TAU;
        const len = 16 + Math.floor(Math.random() * 16);
        for (let k = 0; k < len; k++) {
          const f = k / len;                         // 0 = head ... 1 = end of tail
          parts.push({
            orbit: orbit + (Math.random() - 0.5) * 0.012,
            ang: head - Math.sign(speed) * k * 0.024,
            speed, plane: s % 3,
            size: 0.45 + (1 - f) ** 1.5 * 1.7,
            bright: (1 - f) ** 1.3,
          });
        }
      }
    }
    for (let i = 0; i < (dense ? 70 : 36); i++) {
      parts.push({
        orbit: 0.44 + Math.random() * 0.68, ang: Math.random() * TAU,
        speed: (0.04 + Math.random() * 0.1) * (Math.random() < 0.5 ? -1 : 1),
        plane: i % 3, size: 0.45 + Math.random() * 0.7, bright: Math.random() * 0.35,
      });
    }
    return parts;
  }

  _monitor(now) {
    // Adapt quality if frames are consistently slow (weak GPU / huge window)
    const ft = this._frameTimes;
    ft.push(now);
    if (ft.length > 90) ft.shift();
    if (ft.length === 90 && this.quality === 'high') {
      const avg = (ft[89] - ft[0]) / 89;
      if (avg > 24 && !document.hidden) {
        this.quality = 'low';
        this.particles = this._makeParticles(false);
        this.onFrameRate?.('low');
      }
    }
  }

  _update(dt) {
    const motion = this.reduced ? 0.25 : 1;
    for (const s of Object.values(this.springs)) s.step(dt);
    this.base.forEach((s) => s.step(dt));
    this.accent.forEach((s) => s.step(dt));
    this.boost.step(dt);
    this.boost.target = 0;

    const p = this._p = Object.fromEntries(Object.entries(this.springs).map(([k, s]) => [k, s.value]));
    p.energy = Math.min(1.3, p.energy + Math.max(0, this.boost.value) * 0.25);
    this.t += dt * motion;

    const spin = p.spin * motion;
    this.rot.a += dt * spin * 0.06;
    this.rot.b -= dt * spin * 0.22;
    this.rot.c += dt * spin * 0.35;
    this.rot.d -= dt * spin * 0.12;
    this.rot.sweep += dt * (0.6 + p.sweep * 2.2) * motion;
    this.rot.pulse += dt * (0.8 + spin * 1.6);

    // Mic level: quick attack, slow release; history feeds the waveform
    const raw = this.state === 'listening' ? this.getLevel() : 0;
    this.level += (raw - this.level) * Math.min(1, dt * (raw > this.level ? 20 : 5));
    this.histTimer += dt;
    if (this.histTimer > 0.035) {
      this.histTimer = 0;
      this.levelHist.copyWithin(1, 0);
      this.levelHist[0] = this.level;
    }

    // Synthetic speech envelope (SAPI exposes no audio level): syllable-like bursts
    const sp = this.speech;
    sp.timer -= dt;
    if (sp.timer <= 0) {
      sp.timer = 0.09 + Math.random() * 0.16;
      sp.target = this.state === 'speaking' ? (Math.random() < 0.18 ? 0.15 : 0.45 + Math.random() * 0.55) : 0;
    }
    sp.env += (sp.target - sp.env) * Math.min(1, dt * 14);

    // Emitted light pulses
    this.pulseTimer -= dt;
    if (!this.reduced && this.pulseTimer <= 0) {
      if (this.state === 'speaking' && sp.env > 0.75) { this.emitPulse(0.45); this.pulseTimer = 0.42; }
      else if (this.state === 'listening' && this.level > 0.55) { this.emitPulse(0.4); this.pulseTimer = 0.5; }
      else if (this.state === 'thinking') { this.emitPulse(0.32); this.pulseTimer = 0.95; }
      else this.pulseTimer = 0.2;
    }
    for (const pulse of this.pulses) pulse.p += dt * 0.55;
    this.pulses = this.pulses.filter((pulse) => pulse.p < 1);

    for (const plane of PLANES) plane.node += plane.drift * dt * motion;
    const swarm = p.swarm * motion;
    for (const pt of this.particles) pt.ang += pt.speed * dt * swarm;
  }

  // ---------------------------------------------------------------------------
  _draw() {
    const { ctx, size, dpr } = this;
    const p = this._p;
    const c = this.base.map((s) => s.value);
    const acc = this.accent.map((s) => s.value);
    const hi = mix(c, WHITE, 0.72);
    const E = p.energy;
    const cx = size / 2, cy = size / 2;
    const R = size * 0.355;
    const t = this.t;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, size, size);
    ctx.globalCompositeOperation = 'lighter';
    ctx.lineCap = 'round';

    // 1. Ambient glow
    let g = ctx.createRadialGradient(cx, cy, R * 0.15, cx, cy, R * 1.3);
    g.addColorStop(0, rgba(c, 0.15 * E));
    g.addColorStop(0.5, rgba(c, 0.045 * E));
    g.addColorStop(1, rgba(c, 0));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);

    // 2. Orbital guides (projected circles of the particle planes)
    ctx.lineWidth = 1;
    for (const plane of PLANES) {
      ctx.beginPath();
      for (let i = 0; i <= 72; i++) {
        const [x, y] = this._project(R * 0.84, (i / 72) * TAU, plane, cx, cy, R);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.strokeStyle = rgba(c, 0.045 + 0.03 * E);
      ctx.stroke();
    }

    // 3. Radar sweep (processing)
    if (p.sweep > 0.02) {
      const span = 0.75;
      const cg = ctx.createConicGradient(this.rot.sweep - span, cx, cy);
      cg.addColorStop(0, rgba(c, 0));
      cg.addColorStop(span / TAU, rgba(c, 0.2 * p.sweep));
      cg.addColorStop(span / TAU + 0.001, rgba(c, 0));
      cg.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = cg;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.97, 0, TAU);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(this.rot.sweep) * R * 0.32, cy + Math.sin(this.rot.sweep) * R * 0.32);
      ctx.lineTo(cx + Math.cos(this.rot.sweep) * R * 0.97, cy + Math.sin(this.rot.sweep) * R * 0.97);
      ctx.strokeStyle = rgba(hi, 0.45 * p.sweep);
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }

    // Particles split by depth so the sphere sits between them
    const { back, front } = this._particleBuckets(cx, cy, R);
    this._drawParticles(back, mix(c, acc, p.violet), 0.55);

    // 4. Tick ring (outer)
    this._tickRing(cx, cy, R * 1.05, R, c, E);

    // 5. Arc ring + travelling light pulse
    this._arcRing(cx, cy, R * 0.9, c, hi, E);

    // 6. Dashed ring
    ctx.setLineDash([1.4, 6]);
    ctx.lineDashOffset = this.rot.c * R * 0.8;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 0.8, 0, TAU);
    ctx.lineWidth = 1.3;
    ctx.strokeStyle = rgba(c, 0.32 + 0.18 * E);
    ctx.stroke();
    ctx.setLineDash([]);

    // 7. Bracket ring
    this._brackets(cx, cy, R * 0.7, c, E);

    // 8. Energy segments (light flowing around a segmented ring)
    this._segments(cx, cy, R * 0.62, c, hi, E);

    // 9. Reactive waveform ring
    this._waveRing(cx, cy, R, c, hi, p);

    // 10. Emitted pulses
    for (const pulse of this.pulses) {
      const r = R * (0.34 + pulse.p * 0.72);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, TAU);
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = rgba(hi, pulse.s * (1 - pulse.p) ** 2 * 0.6);
      ctx.stroke();
    }

    // 11. Energy sphere
    this._sphere(cx, cy, R, c, acc, hi, p);

    // 12. Near-side particles
    this._drawParticles(front, mix(c, acc, p.violet * 0.8), 1);

    // 13. Bloom
    if (this.quality === 'high' && !this.reduced) {
      const b = this.bctx;
      b.globalCompositeOperation = 'copy';
      b.filter = `blur(${Math.max(2, Math.round(this.bloom.width / 70))}px)`;
      b.drawImage(this.canvas, 0, 0, this.bloom.width, this.bloom.height);
      b.filter = 'none';
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalAlpha = 0.62;
      ctx.drawImage(this.bloom, 0, 0, this.canvas.width, this.canvas.height);
      ctx.globalAlpha = 1;
    }
  }

  _tickRing(cx, cy, r, R, c, E) {
    const ctx = this.ctx;
    const minor = new Path2D(), major = new Path2D();
    for (let i = 0; i < 144; i++) {
      const a = this.rot.a + (i / 144) * TAU;
      const isMajor = i % 12 === 0;
      const r0 = r - (isMajor ? R * 0.055 : R * 0.022);
      const path = isMajor ? major : minor;
      const cos = Math.cos(a), sin = Math.sin(a);
      path.moveTo(cx + cos * r0, cy + sin * r0);
      path.lineTo(cx + cos * r, cy + sin * r);
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(c, 0.16 + 0.12 * E);
    ctx.stroke(minor);
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = rgba(c, 0.38 + 0.25 * E);
    ctx.stroke(major);
    ctx.beginPath();
    ctx.arc(cx, cy, r + R * 0.04, 0, TAU);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(c, 0.07 + 0.04 * E);
    ctx.stroke();
  }

  _arcRing(cx, cy, r, c, hi, E) {
    const ctx = this.ctx;
    const segs = [[0, 1.15], [1.5, 2.3], [2.75, 4.55], [4.95, 5.85]];
    const rot = this.rot.b;
    for (const [w, a] of [[7, 0.06 * E], [2.2, 0.5 + 0.3 * E]]) {
      ctx.lineWidth = w;
      ctx.strokeStyle = rgba(c, a);
      ctx.beginPath();
      for (const [s0, s1] of segs) {
        ctx.moveTo(cx + Math.cos(rot + s0) * r, cy + Math.sin(rot + s0) * r);
        ctx.arc(cx, cy, r, rot + s0, rot + s1);
      }
      ctx.stroke();
    }
    // Light pulse racing around the ring with a fading tail
    const head = this.rot.pulse;
    for (let k = 0; k < 12; k++) {
      const a1 = head - k * 0.045, a0 = a1 - 0.05;
      ctx.beginPath();
      ctx.arc(cx, cy, r, a0, a1);
      ctx.lineWidth = 2.6 - k * 0.12;
      ctx.strokeStyle = rgba(hi, (0.95 - k * 0.075) * (0.45 + 0.55 * E));
      ctx.stroke();
    }
  }

  _brackets(cx, cy, r, c, E) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TAU);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(c, 0.06);
    ctx.stroke();
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = rgba(c, 0.32 + 0.3 * E);
    ctx.fillStyle = rgba(c, 0.6 + 0.3 * E);
    for (let i = 0; i < 4; i++) {
      const mid = this.rot.d + i * (TAU / 4) + Math.PI / 4;
      const a0 = mid - 0.32, a1 = mid + 0.32;
      ctx.beginPath();
      ctx.arc(cx, cy, r, a0, a1);
      ctx.stroke();
      for (const a of [a0, a1]) {
        ctx.beginPath();
        ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 1.8, 0, TAU);
        ctx.fill();
      }
    }
  }

  _segments(cx, cy, r, c, hi, E) {
    const ctx = this.ctx;
    const n = 64, gap = 0.035;
    const buckets = [new Path2D(), new Path2D(), new Path2D(), new Path2D()];
    for (let i = 0; i < n; i++) {
      const a0 = (i / n) * TAU + gap, a1 = ((i + 1) / n) * TAU - gap;
      const flow = Math.max(0, Math.sin(i * 0.3 - this.t * 2.4 * (0.5 + this._p.spin * 0.5)));
      const v = Math.pow(flow, 5) * E;
      const b = v > 0.6 ? 3 : v > 0.3 ? 2 : v > 0.08 ? 1 : 0;
      buckets[b].moveTo(cx + Math.cos(a0) * r, cy + Math.sin(a0) * r);
      buckets[b].arc(cx, cy, r, a0, a1);
    }
    const styles = [[c, 0.07], [c, 0.25], [hi, 0.5], [hi, 0.85]];
    ctx.lineWidth = 2.2;
    buckets.forEach((path, i) => { ctx.strokeStyle = rgba(styles[i][0], styles[i][1]); ctx.stroke(path); });
  }

  _waveRing(cx, cy, R, c, hi, p) {
    const ctx = this.ctx;
    const t = this.t;
    const N = 180;
    const base = R * 0.5;
    const hist = this.levelHist, H = hist.length;
    const lvl = this.level, sp = this.speech.env;
    const pathA = new Path2D(), pathB = new Path2D();

    for (let i = 0; i <= N; i++) {
      const a = (i / N) * TAU;
      // Mirror the level history around the ring (newest at the top)
      const u = (i <= N / 2 ? i : N - i) / (N / 2) * (H - 1);
      const i0 = u | 0, frac = u - i0;
      const h = hist[i0] * (1 - frac) + hist[Math.min(H - 1, i0 + 1)] * frac;

      const idle = Math.sin(a * 9 - t * 1.1) * 0.55 + Math.sin(a * 14 + t * 0.8) * 0.45;
      const listen = h * (0.65 + 0.35 * Math.sin(a * 9 + t * 7)) + lvl * 0.45 * Math.sin(a * 3 - t * 4);
      const speak = sp * (0.6 * Math.sin(a * 5 + t * 5.5) + 0.4 * Math.sin(a * 11 - t * 8.5));
      const think = Math.pow(Math.abs(Math.sin(a * 9 + t * 3.2)), 18) - 0.08;

      const amp = R * p.wave * (0.0065 * p.idleW * idle + 0.15 * p.listenW * listen
        + 0.085 * p.speakW * speak + 0.055 * p.thinkW * think);
      const rA = base + amp;
      const rB = base * 0.9 - amp * 0.55;
      const cos = Math.cos(a - Math.PI / 2), sin = Math.sin(a - Math.PI / 2);
      if (i) { pathA.lineTo(cx + cos * rA, cy + sin * rA); pathB.lineTo(cx + cos * rB, cy + sin * rB); }
      else { pathA.moveTo(cx + cos * rA, cy + sin * rA); pathB.moveTo(cx + cos * rB, cy + sin * rB); }
    }

    const E = p.energy;
    ctx.lineJoin = 'round';
    ctx.lineWidth = 8; ctx.strokeStyle = rgba(c, 0.05 + 0.04 * E); ctx.stroke(pathA);
    ctx.lineWidth = 2.8; ctx.strokeStyle = rgba(c, 0.18 + 0.12 * E); ctx.stroke(pathA);
    const active = Math.min(1, p.listenW + p.speakW + p.thinkW);
    ctx.lineWidth = 1.2; ctx.strokeStyle = rgba(mix(c, hi, 0.35 + 0.65 * active), 0.42 + 0.48 * E); ctx.stroke(pathA);
    ctx.lineWidth = 1; ctx.strokeStyle = rgba(c, 0.18 + 0.2 * E); ctx.stroke(pathB);
  }

  _sphere(cx, cy, R, c, acc, hi, p) {
    const ctx = this.ctx;
    const t = this.t, E = p.energy;
    const Rs = R * 0.27 * (1 + 0.12 * this.level * p.listenW + 0.07 * this.speech.env * p.speakW
      + 0.025 * Math.sin(t * 1.5) + 0.05 * Math.max(0, this.boost.value));

    // Halo
    let g = ctx.createRadialGradient(cx, cy, Rs * 0.4, cx, cy, Rs * 2.5);
    g.addColorStop(0, rgba(c, 0.36 * E));
    g.addColorStop(0.35, rgba(c, 0.12 * E));
    g.addColorStop(1, rgba(c, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, Rs * 2.5, 0, TAU);
    ctx.fill();

    // Body - lit from the upper left like a glass sphere
    ctx.globalCompositeOperation = 'source-over';
    g = ctx.createRadialGradient(cx - Rs * 0.25, cy - Rs * 0.3, Rs * 0.04, cx, cy, Rs);
    g.addColorStop(0, rgba(hi, 0.95));
    g.addColorStop(0.22, rgba(mix(hi, c, 0.4), 0.7));
    g.addColorStop(0.6, rgba(mix(c, [10, 30, 60], 0.45), 0.55));
    g.addColorStop(1, rgba(mix(c, [6, 16, 34], 0.7), 0.5));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, Rs, 0, TAU);
    ctx.fill();
    ctx.globalCompositeOperation = 'lighter';

    // Plasma currents inside
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, Rs, 0, TAU);
    ctx.clip();
    for (let k = 0; k < 3; k++) {
      const sp = 0.55 + k * 0.3 + p.spin * 0.15;
      const x = cx + Math.cos(t * sp + k * 2.1) * Rs * 0.42;
      const y = cy + Math.sin(t * sp * 1.27 + k * 1.3) * Rs * 0.42;
      g = ctx.createRadialGradient(x, y, 0, x, y, Rs * 0.8);
      g.addColorStop(0, rgba(k === 1 ? acc : c, 0.34 * E));
      g.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = g;
      ctx.fillRect(cx - Rs, cy - Rs, Rs * 2, Rs * 2);
    }
    ctx.restore();

    // Fresnel rim + orbiting highlights
    ctx.beginPath();
    ctx.arc(cx, cy, Rs, 0, TAU);
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = rgba(hi, 0.4 + 0.3 * E);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, Rs * 1.16, 0, TAU);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(c, 0.18 + 0.1 * E);
    ctx.stroke();
    for (let k = 0; k < 2; k++) {
      const a = this.rot.pulse * 1.7 + k * Math.PI;
      ctx.beginPath();
      ctx.arc(cx, cy, Rs * 1.16, a, a + 0.5);
      ctx.lineWidth = 2;
      ctx.strokeStyle = rgba(hi, 0.7 * E);
      ctx.stroke();
    }

    // Specular highlight
    ctx.save();
    ctx.translate(cx - Rs * 0.36, cy - Rs * 0.42);
    ctx.rotate(-0.6);
    ctx.scale(1, 0.55);
    g = ctx.createRadialGradient(0, 0, 0, 0, 0, Rs * 0.38);
    g.addColorStop(0, 'rgba(255,255,255,0.45)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(0, 0, Rs * 0.38, 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  _project(r, ang, plane, cx, cy, R) {
    const x0 = r * Math.cos(ang), y0 = r * Math.sin(ang);
    const y1 = y0 * Math.cos(plane.inc), z = y0 * Math.sin(plane.inc);
    const cn = Math.cos(plane.node), sn = Math.sin(plane.node);
    const x = x0 * cn - y1 * sn, y = x0 * sn + y1 * cn;
    const s = 1 / (1 - z / (R * 8));
    return [cx + x * s, cy + y * s, z, s];
  }

  _particleBuckets(cx, cy, R) {
    const back = [[], [], [], []], front = [[], [], [], []];
    const sphereR2 = (R * 0.3) ** 2;
    for (const pt of this.particles) {
      const r = pt.orbit * R;
      const [x, y, z, s] = this._project(r, pt.ang, PLANES[pt.plane], cx, cy, R);
      if (z < 0 && (x - cx) ** 2 + (y - cy) ** 2 < sphereR2) continue;   // hidden behind the sphere
      const depth = z / r * 0.5 + 0.5;                                    // 0 far .. 1 near
      const lvl = Math.min(3, Math.floor((pt.bright * 0.75 + depth * 0.25) * 4));
      (z < 0 ? back : front)[lvl].push(x, y, pt.size * s * (0.75 + depth * 0.4));
    }
    return { back, front };
  }

  _drawParticles(buckets, color, scale) {
    const ctx = this.ctx;
    const vis = Math.min(1, 0.4 + this._p.swarm * 0.4) * scale;
    const alphas = [0.16, 0.34, 0.6, 0.95];
    buckets.forEach((list, lvl) => {
      if (!list.length) return;
      const path = new Path2D();
      for (let i = 0; i < list.length; i += 3) {
        path.moveTo(list[i] + list[i + 2], list[i + 1]);
        path.arc(list[i], list[i + 1], list[i + 2], 0, TAU);
      }
      ctx.fillStyle = rgba(lvl === 3 ? mix(color, WHITE, 0.55) : color, alphas[lvl] * vis);
      ctx.fill(path);
    });
  }
}

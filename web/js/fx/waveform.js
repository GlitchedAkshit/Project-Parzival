// Mirrored bar waveform around the microphone button.
//  listening -> real microphone level history from the core
//  speaking  -> a synthetic speech envelope (Windows SAPI exposes no audio level)
//  otherwise -> a calm dotted baseline, drawn once (no animation loop at all)

export class VoiceWave {
  constructor(canvas, { getLevel }) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.getLevel = getLevel;
    this.mode = 'idle';
    this.bars = new Float32Array(34);
    this.env = 0;
    this.envTarget = 0;
    this.envTimer = 0;
    this.color = [63, 224, 255];
    this._raf = 0;
    this._last = 0;
    new ResizeObserver(() => this._resize()).observe(canvas);
    this._resize();
  }

  setMode(mode, rgb) {
    if (rgb) this.color = rgb;
    if (mode === this.mode) return;
    this.mode = mode;
    this._ensureLoop();   // in idle the loop lets the bars fall, then stops itself
  }

  _resize() {
    const r = this.canvas.getBoundingClientRect();
    if (!r.width) return;
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.w = r.width;
    this.h = r.height;
    this.canvas.width = Math.round(r.width * this.dpr);
    this.canvas.height = Math.round(r.height * this.dpr);
    this._draw();
  }

  _ensureLoop() {
    if (this._raf) return;
    const loop = (now) => {
      const dt = this._last ? Math.min(0.05, (now - this._last) / 1000) : 1 / 60;
      this._last = now;
      const moving = this._step(dt);
      this._draw();
      if (this.mode === 'idle' && !moving) { this._raf = 0; this._last = 0; return; }
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  _step(dt) {
    let input = 0;
    if (this.mode === 'listening') input = this.getLevel();
    else if (this.mode === 'speaking') {
      this.envTimer -= dt;
      if (this.envTimer <= 0) {
        this.envTimer = 0.08 + Math.random() * 0.14;
        this.envTarget = Math.random() < 0.15 ? 0.1 : 0.35 + Math.random() * 0.6;
      }
      this.env += (this.envTarget - this.env) * Math.min(1, dt * 16);
      input = this.env;
    } else if (this.mode === 'thinking') {
      input = 0.12 + 0.08 * Math.sin(performance.now() / 180);
    }

    // Shift history outward from the centre: newest bar sits next to the mic
    this._acc = (this._acc || 0) + dt;
    if (this._acc > 0.045) {
      this._acc = 0;
      this.bars.copyWithin(1, 0);
      this.bars[0] = input;
    }
    let energy = 0;
    if (this.mode === 'idle') {
      for (let i = 0; i < this.bars.length; i++) { this.bars[i] *= 0.86; energy += this.bars[i]; }
    } else {
      for (let i = 0; i < this.bars.length; i++) energy += this.bars[i];
    }
    return energy > 0.01;
  }

  _draw() {
    const { ctx, w, h, dpr } = this;
    if (!w) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const [r, g, b] = this.color;
    const cx = w / 2, cy = h / 2;
    const gapFromCenter = 58;
    const step = Math.max(6, (w / 2 - gapFromCenter) / this.bars.length);
    const barW = Math.max(2, step * 0.42);
    const maxH = h * 0.42;

    for (let i = 0; i < this.bars.length; i++) {
      const x = gapFromCenter + i * step;
      if (x > w / 2 - 4) break;
      const fade = 1 - i / this.bars.length;
      const v = this.bars[i];
      const bh = Math.max(barW, v * maxH * (0.55 + 0.45 * fade) + barW);
      const alpha = (0.12 + Math.min(1, v * 1.6) * 0.75) * (0.25 + 0.75 * fade);
      ctx.fillStyle = `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
      for (const side of [-1, 1]) {
        const bx = cx + side * x - barW / 2;
        roundRect(ctx, bx, cy - bh / 2, barW, bh, barW / 2);
      }
    }
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

// Extremely subtle starfield / floating particles. Drawn at ~24 fps (the
// motion is slow enough that more frames buy nothing) and paused when the
// window is hidden or effects are reduced, so the glass panels' backdrop
// blur isn't recomputed more often than necessary.
import { prefersReducedMotion } from '../dom.js';

export function initStarfield(canvas) {
  const ctx = canvas.getContext('2d', { alpha: true });
  let w = 0, h = 0, dpr = 1;
  let stars = [];
  let last = 0;

  const build = () => {
    dpr = Math.min(devicePixelRatio || 1, 1.5);
    const rect = canvas.getBoundingClientRect();
    w = rect.width; h = rect.height;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const count = Math.round(Math.min(260, (w * h) / 9000));
    stars = Array.from({ length: count }, () => {
      const depth = Math.random();
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        r: 0.35 + depth * 0.95,
        a: 0.12 + depth * 0.5,
        tw: 0.4 + Math.random() * 1.4,
        ph: Math.random() * Math.PI * 2,
        vx: (0.6 + depth * 2.2) * (Math.random() < 0.5 ? -1 : 1),
        vy: -(0.4 + depth * 1.6),
        cyan: Math.random() < 0.35,
      };
    });
    draw(performance.now(), 0);
  };

  const draw = (now, dt) => {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const t = now / 1000;
    for (const s of stars) {
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      if (s.x < -4) s.x = w + 4; else if (s.x > w + 4) s.x = -4;
      if (s.y < -4) { s.y = h + 4; s.x = Math.random() * w; }
      const alpha = s.a * (0.65 + 0.35 * Math.sin(t * s.tw + s.ph));
      ctx.fillStyle = s.cyan ? `rgba(120, 225, 255, ${alpha})` : `rgba(215, 238, 255, ${alpha * 0.85})`;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
  };

  const loop = (now) => {
    requestAnimationFrame(loop);
    if (document.hidden || prefersReducedMotion()) { last = now; return; }
    const elapsed = now - last;
    if (elapsed < 1000 / 24) return;
    draw(now, Math.min(elapsed, 100) / 1000);
    last = now;
  };

  new ResizeObserver(build).observe(canvas);
  requestAnimationFrame(loop);
}

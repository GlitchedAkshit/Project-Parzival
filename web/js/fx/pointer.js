// Pointer-reactive lighting and parallax.
//  - background layers ([data-depth]) drift opposite the pointer
//  - a soft ambient light follows the pointer (moved with transform only)
//  - the hovered glass panel gets an edge light / sheen at the pointer
//  - the AI core tilts slightly toward the pointer
// Everything eases in a single rAF loop that sleeps when nothing moves.
import { prefersReducedMotion } from '../dom.js';

export function initPointerFx({ core }) {
  const layers = [...document.querySelectorAll('.env [data-depth]')].map((el) => ({
    el, depth: parseFloat(el.dataset.depth) || 0,
  }));
  const root = document.documentElement;
  const target = { x: 0, y: 0, px: innerWidth / 2, py: innerHeight * 0.4 };
  const cur = { ...target };
  let running = false;
  let litPanel = null;

  const tick = () => {
    const k = 0.075;
    cur.x += (target.x - cur.x) * k;
    cur.y += (target.y - cur.y) * k;
    cur.px += (target.px - cur.px) * 0.16;
    cur.py += (target.py - cur.py) * 0.16;

    for (const { el, depth } of layers) {
      el.style.transform = `translate3d(${(-cur.x * 26 * depth).toFixed(2)}px, ${(-cur.y * 18 * depth).toFixed(2)}px, 0)`;
    }
    root.style.setProperty('--spot-x', `${cur.px.toFixed(1)}px`);
    root.style.setProperty('--spot-y', `${cur.py.toFixed(1)}px`);

    const settled = Math.abs(target.x - cur.x) < 0.0008 && Math.abs(target.y - cur.y) < 0.0008
      && Math.abs(target.px - cur.px) < 0.5 && Math.abs(target.py - cur.py) < 0.5;
    if (settled) { running = false; return; }
    requestAnimationFrame(tick);
  };

  const kick = () => {
    if (!running && !prefersReducedMotion()) { running = true; requestAnimationFrame(tick); }
  };

  addEventListener('pointermove', (e) => {
    document.body.classList.add('has-pointer');
    target.x = (e.clientX / innerWidth) * 2 - 1;
    target.y = (e.clientY / innerHeight) * 2 - 1;
    target.px = e.clientX;
    target.py = e.clientY;
    kick();

    // Edge light on the glass panel under the pointer
    const panel = e.target.closest?.('.glass');
    if (panel !== litPanel) {
      litPanel?.classList.remove('is-lit');
      litPanel = panel;
      panel?.classList.add('is-lit');
    }
    if (panel) {
      const r = panel.getBoundingClientRect();
      panel.style.setProperty('--lx', `${(e.clientX - r.left).toFixed(0)}px`);
      panel.style.setProperty('--ly', `${(e.clientY - r.top).toFixed(0)}px`);
    }
  }, { passive: true });

  document.addEventListener('pointerleave', () => {
    litPanel?.classList.remove('is-lit');
    litPanel = null;
    target.x = target.y = 0;
    kick();
  });

  // Core tilt toward the pointer while hovering it
  if (core) {
    core.addEventListener('pointermove', (e) => {
      if (prefersReducedMotion()) return;
      const r = core.getBoundingClientRect();
      const dx = (e.clientX - r.left) / r.width - 0.5;
      const dy = (e.clientY - r.top) / r.height - 0.5;
      core.style.setProperty('--tilt-y', `${(dx * 9).toFixed(2)}deg`);
      core.style.setProperty('--tilt-x', `${(-dy * 9).toFixed(2)}deg`);
    }, { passive: true });
    core.addEventListener('pointerleave', () => {
      core.style.setProperty('--tilt-x', '0deg');
      core.style.setProperty('--tilt-y', '0deg');
    });
  }
}

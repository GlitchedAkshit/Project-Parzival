// Workspace sheet: Search, Applications, System, Tasks, Smart home, Settings,
// Activity. Opening it expands the sheet out of the dock button that was
// pressed, while the AI core morphs into a compact orb beside it (wide
// layouts) - closing reverses both.
import { icon } from '../dom.js';
import { store, update } from '../store.js';

/** Sum of offsetLeft/offsetTop up to `ancestor` - unaffected by CSS transforms. */
function offsetWithin(el, ancestor) {
  let x = 0, y = 0, node = el;
  while (node && node !== ancestor) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent;
  }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}

export function initSheet({ views }) {
  const app = document.getElementById('app');
  const sheet = document.getElementById('sheet');
  const body = document.getElementById('sheet-body');
  const titleEl = document.getElementById('sheet-title');
  const descEl = document.getElementById('sheet-desc');
  const iconEl = document.getElementById('sheet-icon');
  const closeBtn = document.getElementById('sheet-close');
  const stage = document.getElementById('stage');
  closeBtn.append(icon('close'));
  closeBtn.addEventListener('click', () => close());

  const mounted = {};
  let current = null;
  let leaveTimer = 0;

  // ---- compact core geometry ---------------------------------------------------
  const layoutCompact = () => {
    const root = document.documentElement.style;
    if (innerWidth < 1024) {                       // narrow: sheet is a full overlay
      sheet.style.setProperty('--sheet-offset', '0px');
      delete app.dataset.compact;
      return;
    }
    const stageW = stage.clientWidth;
    const sheetNatural = sheet.parentElement.clientWidth - offsetWithin(stage, sheet.parentElement).x;
    const strip = Math.round(Math.min(280, Math.max(210, stageW * 0.3)));
    if (sheetNatural - strip - 18 < 520) {           // no room for the mini core
      app.dataset.compact = 'none';
      sheet.style.setProperty('--sheet-offset', '0px');
      return;
    }
    app.dataset.compact = 'strip';
    sheet.style.setProperty('--sheet-offset', `${strip + 18}px`);

    const core = document.getElementById('core');
    const label = stage.querySelector('.core__label');
    const voice = document.getElementById('voice');
    const mic = document.getElementById('mic-btn');

    const c = offsetWithin(core, stage);
    const size = Math.min(strip - 30, 230);
    const top = Math.max(14, stage.clientHeight * 0.08);
    const cx = strip / 2, cy = top + size / 2;
    root.setProperty('--core-tx', `${(cx - (c.x + c.w / 2)).toFixed(1)}px`);
    root.setProperty('--core-ty', `${(cy - (c.y + c.h / 2)).toFixed(1)}px`);
    root.setProperty('--core-s', (size / c.w).toFixed(4));

    const l = offsetWithin(label, stage);
    const labelTop = cy + size / 2 + 8;
    root.setProperty('--label-tx', `${(cx - (l.x + l.w / 2)).toFixed(1)}px`);
    root.setProperty('--label-ty', `${(labelTop - l.y).toFixed(1)}px`);

    // Put the mic's centre under the label, accounting for the voice block's 0.86 scale
    const v = offsetWithin(voice, stage);
    const m = offsetWithin(mic, stage);
    const vcx = v.x + v.w / 2, vcy = v.y + v.h / 2;
    const mcx = m.x + m.w / 2, mcy = m.y + m.h / 2;
    const targetY = labelTop + l.h + 30 + (m.h * 0.86) / 2;
    root.setProperty('--voice-tx', `${(cx - vcx - (mcx - vcx) * 0.86).toFixed(1)}px`);
    root.setProperty('--voice-ty', `${(targetY - vcy - (mcy - vcy) * 0.86).toFixed(1)}px`);
  };

  addEventListener('resize', () => { if (current) layoutCompact(); });

  // ---- open / switch / close ------------------------------------------------------
  const mount = (id) => {
    if (!mounted[id]) {
      const view = views[id].create();
      view.el.classList.add('view');
      view.el.hidden = true;
      body.append(view.el);
      mounted[id] = view;
    }
    return mounted[id];
  };

  const showView = (id) => {
    const def = views[id];
    for (const [key, view] of Object.entries(mounted)) {
      if (key !== id && !view.el.hidden) { view.el.hidden = true; view.onHide?.(); }
    }
    const view = mount(id);
    titleEl.textContent = def.title;
    descEl.textContent = def.desc;
    iconEl.replaceChildren(icon(def.icon));
    view.el.hidden = false;
    // Staggered reveal of the view's top-level blocks
    [...view.el.children].forEach((child, i) => {
      child.classList.remove('reveal');
      void child.offsetWidth;
      child.style.setProperty('--i', i);
      child.classList.add('reveal');
    });
    body.scrollTop = 0;
    view.onShow?.(store);
    // Synchronous on purpose: rAF callbacks don't run while the window is in the background
    if (view.focus) view.focus();
    else closeBtn.focus({ preventScroll: true });
  };

  function open(id, originEl) {
    if (!views[id]) return;
    clearTimeout(leaveTimer);
    const wasOpen = current !== null && !sheet.classList.contains('is-leaving');
    current = id;
    update({ view: id });

    if (wasOpen) { showView(id); return; }

    sheet.classList.remove('is-leaving', 'is-entering');
    sheet.hidden = false;
    layoutCompact();
    app.dataset.mode = 'workspace';

    // Expand from the dock button
    if (originEl) {
      const s = sheet.getBoundingClientRect(), b = originEl.getBoundingClientRect();
      sheet.style.setProperty('--sheet-ox', `${b.left + b.width / 2 - s.left}px`);
      sheet.style.setProperty('--sheet-oy', `${b.top + b.height / 2 - s.top}px`);
    }
    void sheet.offsetWidth;
    sheet.classList.add('is-entering');
    showView(id);
  }

  function close() {
    if (current === null) return;
    const view = mounted[current];
    current = null;
    update({ view: 'assistant' });
    app.dataset.mode = 'assistant';
    sheet.classList.remove('is-entering');
    sheet.classList.add('is-leaving');
    const done = () => {
      if (current !== null) return;
      sheet.hidden = true;
      sheet.classList.remove('is-leaving');
      view?.onHide?.();
    };
    sheet.addEventListener('animationend', done, { once: true });
    leaveTimer = setTimeout(done, 400);   // if animations are off
  }

  // Let views react to live data while they're visible
  const notify = (s, keys) => {
    if (current && mounted[current]?.update) mounted[current].update(s, keys);
  };

  return { open, close, isOpen: () => current !== null, current: () => current, notify };
}

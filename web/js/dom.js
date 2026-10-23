// Tiny DOM helpers - no framework needed for a UI this size.
import { icon } from './icons.js';

/**
 * h('button.btn.btn--primary', { onclick, 'aria-label': 'x' }, 'Text', child)
 * Props starting with "on" become listeners; `dataset`/`style` objects merge;
 * everything else is set as an attribute (true -> empty attribute).
 */
export function h(spec, props = {}, ...children) {
  const [tag, ...classes] = spec.split('.');
  const el = document.createElement(tag || 'div');
  if (classes.length) el.className = classes.join(' ');
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key === 'class') el.className += ` ${value}`;
    else if (key === 'text') el.textContent = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export { icon };

export function iconButton(name, label, onclick, extra = {}) {
  return h('button.icon-btn', { type: 'button', 'aria-label': label, 'data-tip': label, onclick, ...extra }, icon(name));
}

export function setIcon(el, name) {
  el.replaceChildren(icon(name));
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function clear(el) {
  el.replaceChildren();
  return el;
}

// ---- Formatting ------------------------------------------------------------
export function fmtClock(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function fmtDay(ts) {
  return new Date(ts * 1000).toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

export function relTime(ts, now = Date.now() / 1000) {
  const d = Math.round(now - ts);
  if (d < 10) return 'now';
  if (d < 60) return `${d}s`;
  if (d < 3600) return `${Math.floor(d / 60)}m`;
  if (d < 86400) return `${Math.floor(d / 3600)}h`;
  return `${Math.floor(d / 86400)}d`;
}

export function dueLabel(due, now = Date.now() / 1000) {
  const d = Math.round(due - now);
  if (d <= 0) return { text: 'due', overdue: true };
  if (d < 60) return { text: `in ${d}s`, overdue: false };
  if (d < 3600) return { text: `in ${Math.round(d / 60)}m`, overdue: false };
  if (d < 86400) {
    const hrs = Math.floor(d / 3600), mins = Math.round((d % 3600) / 60);
    return { text: mins ? `in ${hrs}h ${mins}m` : `in ${hrs}h`, overdue: false };
  }
  return { text: new Date(due * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' }), overdue: false };
}

export function fmtDuration(seconds) {
  const d = Math.floor(seconds / 86400), hr = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${hr}h`;
  if (hr) return `${hr}h ${m}m`;
  return `${m}m`;
}

/** Highlights case-insensitive matches of `query` inside `text` safely. */
export function highlight(text, query) {
  const frag = document.createDocumentFragment();
  if (!query) { frag.append(text); return frag; }
  const lower = text.toLowerCase(), q = query.toLowerCase();
  let i = 0;
  for (;;) {
    const j = lower.indexOf(q, i);
    if (j < 0) { frag.append(text.slice(i)); break; }
    frag.append(text.slice(i, j), h('mark', {}, text.slice(j, j + q.length)));
    i = j + q.length;
  }
  return frag;
}

export function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/** Throttles pointer-ish handlers to one call per animation frame. */
export function rafThrottle(fn) {
  let queued = false, lastArgs;
  return (...args) => {
    lastArgs = args;
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; fn(...lastArgs); });
  };
}

export function prefersReducedMotion() {
  return matchMedia('(prefers-reduced-motion: reduce)').matches
    || document.documentElement.dataset.effects === 'reduced';
}

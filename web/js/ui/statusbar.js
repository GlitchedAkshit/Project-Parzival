// A. Top status bar: identity + system state, live clock, real meters only.
import { h } from '../dom.js';
import { store, subscribe } from '../store.js';

const STATE_TEXT = {
  loading: 'INITIALIZING',
  idle: 'SYSTEM ONLINE',
  listening: 'LISTENING',
  thinking: 'PROCESSING',
  speaking: 'SPEAKING',
};

export function systemStateText() {
  const core = store.core;
  if (store.link === 'offline') return 'CORE OFFLINE';
  if (!core) return 'INITIALIZING';
  if (core.restarting) return 'RESTARTING';
  if (core.status === 'idle') {
    const degraded = (core.services || []).some((s) => s.status === 'error' && (s.id === 'mic' || s.id === 'llm'));
    return degraded ? 'ONLINE · DEGRADED' : 'SYSTEM ONLINE';
  }
  return STATE_TEXT[core.status] || core.status.toUpperCase();
}

export function initStatusbar() {
  const timeEl = document.getElementById('clock-time');
  const dateEl = document.getElementById('clock-date');
  const stateEl = document.getElementById('sys-state');
  const meters = document.getElementById('meters');

  const tickClock = () => {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    timeEl.dateTime = now.toISOString();
    dateEl.textContent = now.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
  };
  tickClock();
  setInterval(tickClock, 1000);

  const els = {};
  const meter = (id, label, opts = {}) => {
    if (!els[id]) {
      const dot = h('span.meter__dot', { 'aria-hidden': 'true' });
      const lab = h('span.meter__label', {}, label);
      const value = h('span.meter__value');
      const bar = opts.bar ? h('span.meter__bar', { 'aria-hidden': 'true' }, h('i')) : null;
      const li = h(`li.meter${opts.metric ? '.meter--metric' : ''}${opts.optional ? '.meter--opt' : ''}`, {}, opts.metric ? null : dot, lab, value, bar);
      els[id] = { li, value, bar };
      meters.append(li);
    }
    return els[id];
  };

  const render = () => {
    stateEl.textContent = systemStateText();
    const core = store.core;
    const svc = Object.fromEntries((core?.services || []).map((s) => [s.id, s]));
    const tone = (s) => ({ ok: 'ok', error: 'error', pending: 'pending', off: 'off' }[s?.status] || 'pending');

    const set = (id, label, t, title, value = '', opts) => {
      const m = meter(id, label, opts);
      m.li.dataset.tone = t;
      m.li.title = title;
      m.li.setAttribute('aria-label', `${label}: ${title}`);
      if (m.value.textContent !== value) m.value.textContent = value;
      return m;
    };

    set('link', 'CORE', store.link === 'online' ? 'ok' : store.link === 'offline' ? 'error' : 'pending',
      store.link === 'online' ? 'Connected to the Parzival core' : store.link === 'offline' ? 'Disconnected - reconnecting' : 'Connecting');
    set('mic', 'MIC', tone(svc.mic), svc.mic?.detail || 'Starting');
    set('wake', 'WAKE', svc.wake?.status === 'ok' ? 'ok' : 'off', svc.wake?.detail || '', '', { optional: true });
    set('llm', 'LLM', tone(svc.llm), svc.llm?.detail || 'Checking', '', {});
    set('home', 'HOME', svc.home?.status === 'ok' ? 'ok' : svc.home?.status === 'error' ? 'warn' : 'off',
      svc.home?.detail || '', '', { optional: true });

    // Real metrics only - hidden entirely when the platform can't report them
    const m = store.metrics;
    for (const [id, label, val] of [['cpu', 'CPU', m?.cpu], ['mem', 'MEM', m?.memory]]) {
      if (val === null || val === undefined) {
        els[id]?.li.remove();
        delete els[id];
        continue;
      }
      const el = set(id, label, 'metric', `${label} ${Math.round(val)}%`, `${Math.round(val)}%`, { metric: true, bar: true });
      el.bar?.firstChild.style.setProperty('--v', (val / 100).toFixed(3));
    }
  };

  subscribe((s, keys) => {
    if (keys.some((k) => k === 'core' || k === 'metrics' || k === 'link')) render();
  });
  render();
}

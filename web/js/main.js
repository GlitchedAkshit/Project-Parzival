// Parzival - holographic glass interface. Wires the live event stream from
// the Python core into the UI modules. Visual effects (fx/) are kept apart
// from business logic (api.js / store.js / ui/ / views/).
import { connectEvents, api, post, ApiError, token } from './api.js';
import { store, live, update, subscribe } from './store.js';
import { h } from './dom.js';
import { installSpringEasing } from './fx/spring.js';
import { initStarfield } from './fx/background.js';
import { initPointerFx } from './fx/pointer.js';
import { initStatusbar } from './ui/statusbar.js';
import { initConversation } from './ui/conversation.js';
import { initStage } from './ui/stage.js';
import { mountContext } from './ui/context.js';
import { initDock, DOCK_ITEMS } from './ui/dock.js';
import { initSheet } from './ui/sheet.js';
import { applyPrefs, onPrefsChange } from './prefs.js';
import { createSearchView } from './views/search.js';
import { createAppsView } from './views/apps.js';
import { createSystemView } from './views/system.js';
import { createTasksView } from './views/tasks.js';
import { createHomeView } from './views/home.js';
import { createSettingsView } from './views/settings.js';

const VIEWS = {
  search: { title: 'Search & history', desc: 'Everything Parzival remembers, plus your tasks', icon: 'search', create: createSearchView },
  apps: { title: 'Applications', desc: 'Launch apps on this PC', icon: 'apps', create: createAppsView },
  system: { title: 'System', desc: 'Live metrics, audio, media and security controls', icon: 'system', create: createSystemView },
  tasks: { title: 'Tasks & reminders', desc: 'Reminders are announced aloud when they come due', icon: 'tasks', create: createTasksView },
  home: { title: 'Smart home', desc: 'The same devices Parzival controls by voice', icon: 'home', create: createHomeView },
  activity: {
    title: 'Activity & services', desc: 'Tasks, commands, notifications and connected services', icon: 'activity',
    create: () => { const el = h('div.glass-lite', { style: { padding: '4px 0' } }); mountContext(el, { openView: (id) => select(id) }); return { el }; },
  },
  settings: { title: 'Settings', desc: 'Saved to settings.json on this PC', icon: 'settings', create: createSettingsView },
};

installSpringEasing();
applyPrefs();

initStarfield(document.querySelector('.env__stars'));
const stage = initStage();
initPointerFx({ core: document.getElementById('core') });
onPrefsChange(() => stage.setEffects());
initStatusbar();
const conversation = initConversation();
mountContext(document.getElementById('context'), { openView: (id) => select(id) });
const dock = initDock((id, btn) => select(id, btn));
const sheet = initSheet({ views: VIEWS });
subscribe((s, keys) => sheet.notify(s, keys));

function select(id, originEl) {
  if (id === 'assistant') {
    sheet.close();
    return;
  }
  if (sheet.current() === id) { sheet.close(); return; }   // pressing the active item toggles it
  sheet.open(id, originEl || dock.button(id));
}

// ---- Live connection to the core ----------------------------------------------------
const banner = document.getElementById('link-banner');
const bannerText = document.getElementById('link-banner-text');
let bannerTimer = 0;
let stopEvents = null;

function setLink(status) {
  if (status === store.link) return;
  update({ link: status });
  clearTimeout(bannerTimer);
  if (status === 'offline') {
    // Brief reconnects shouldn't flash a banner; also detect an expired session
    bannerTimer = setTimeout(async () => {
      banner.hidden = false;
      try { await api('state'); } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          bannerText.textContent = 'This window’s session has expired — close it and start Parzival again.';
          stopEvents?.();          // a new token is needed; retrying can't succeed
        }
      }
    }, 1500);
  } else {
    banner.hidden = true;
  }
}

if (!token) {
  banner.hidden = false;
  bannerText.textContent = 'Open Parzival with “python parzival.py” — this page needs the session key it provides.';
} else {
  stopEvents = connectEvents({
    link: setLink,
    state(data) {
      const prev = store.core;
      if (!('transcript' in data)) data.transcript = prev && prev.core_id === data.core_id ? prev.transcript : [];
      update({ core: data });
    },
    level(data) {
      live.level = data.level;
      live.levelAt = performance.now();
    },
    metrics(data) {
      update({ metrics: data, metricsHistory: [...(store.metricsHistory || []), data].slice(-60) });
    },
    devices: (data) => update({ devices: data }),
    tasks: (data) => update({ tasks: data.tasks }),
    memory: (data) => update({ memory: data }),
  });
}

// ---- Keyboard ----------------------------------------------------------------------------
const typing = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);

addEventListener('keydown', (e) => {
  if (e.defaultPrevented) return;
  if (e.key === 'Escape') {
    if (document.querySelector('.modal-backdrop')) return;     // the dialog handles it
    if (sheet.isOpen()) { sheet.close(); e.preventDefault(); return; }
    if (['listening', 'thinking', 'speaking'].includes(store.core?.status)) {
      post('interrupt').catch(() => {});
      e.preventDefault();
    }
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    select('search');
    return;
  }
  if (e.key === '/' && !typing(document.activeElement)) {
    e.preventDefault();
    if (sheet.isOpen()) sheet.close();
    conversation.focus();
    return;
  }
  if (e.altKey && /^[1-9]$/.test(e.key)) {
    const visible = DOCK_ITEMS.filter((item) => !item.sep && dock.button(item.id)?.offsetParent !== null);
    const item = visible[Number(e.key) - 1];
    if (item) { e.preventDefault(); select(item.id); }
  }
});

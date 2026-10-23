// E. Quick command dock. Every item maps to real functionality.
import { h, icon } from '../dom.js';
import { store, subscribe } from '../store.js';

export const DOCK_ITEMS = [
  { id: 'assistant', label: 'Voice assistant', icon: 'core' },
  { id: 'search', label: 'Search & history', icon: 'search' },
  { id: 'apps', label: 'Applications', icon: 'apps' },
  { id: 'system', label: 'System information', icon: 'system' },
  { id: 'tasks', label: 'Tasks & reminders', icon: 'tasks' },
  { id: 'home', label: 'Smart home', icon: 'home' },
  { id: 'activity', label: 'Activity & services', icon: 'activity', only: 'medium' },
  { sep: true },
  { id: 'settings', label: 'Settings', icon: 'settings' },
];

export function initDock(onSelect) {
  const dock = document.getElementById('dock');
  const buttons = {};

  for (const item of DOCK_ITEMS) {
    if (item.sep) { dock.append(h('span.dock__sep', { 'aria-hidden': 'true' })); continue; }
    const badge = h('span.badge');
    const btn = h('button.dock__item', {
      type: 'button',
      'aria-label': item.label,
      'data-tip': item.label,
      dataset: { view: item.id, ...(item.only ? { only: item.only } : {}) },
      onclick: () => onSelect(item.id, btn),
    }, icon(item.icon), item.id === 'tasks' ? badge : null);
    buttons[item.id] = btn;
    dock.append(btn);
  }

  // Arrow keys move along the dock
  dock.addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const items = [...dock.querySelectorAll('.dock__item')].filter((b) => b.offsetParent !== null);
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1
      : (i + (e.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    items[next].focus();
  });

  const render = () => {
    for (const [id, btn] of Object.entries(buttons)) {
      const current = store.view === id;
      btn.setAttribute('aria-current', String(current));
    }
    const pendingCount = (store.tasks || []).filter((t) => !t.done).length;
    const badge = buttons.tasks.querySelector('.badge');
    badge.textContent = pendingCount ? String(pendingCount) : '';
  };
  subscribe((s, keys) => { if (keys.includes('view') || keys.includes('tasks')) render(); });
  render();

  return { button: (id) => buttons[id] };
}

// F. Context panels - collapsible glass sections. Mountable more than once
// (the side rail on wide screens, the Activity sheet on narrower ones).
import { h, icon, iconButton, relTime, dueLabel } from '../dom.js';
import { post } from '../api.js';
import { store, subscribe } from '../store.js';
import { toast } from './feedback.js';

const ACTIVITY_ICON = {
  wake: 'core', listen: 'mic', cancel: 'close', interrupt: 'stop', reply: 'wave', error: 'warn',
  device: 'bulb', system: 'system', reminder: 'bell', task_add: 'tasks', task_list: 'tasks',
  time: 'clock', date: 'clock', tv: 'tv',
};
const NOTE_ICON = { info: 'info', warn: 'warn', error: 'error', reminder: 'bell' };
const OPEN_KEY = 'parzival.context.open';

function loadOpen() {
  try { return JSON.parse(localStorage.getItem(OPEN_KEY)) || { tasks: true, activity: true }; }
  catch { return { tasks: true, activity: true }; }
}

export function sortTasks(tasks) {
  return [...tasks].sort((a, b) => (a.due || Infinity) - (b.due || Infinity) || a.created - b.created);
}

export async function toggleTask(task) {
  try { await post('tasks/update', { id: task.id, done: !task.done }); }
  catch (err) { toast(err.message, 'error'); }
}

// ---- data helpers ---------------------------------------------------------------
const halfMinute = () => Math.floor(Date.now() / 30_000);
const pending = () => sortTasks((store.tasks || []).filter((t) => !t.done));
const notes = () => [...(store.core?.notifications || [])].reverse();
function commands() {
  const seen = new Set();
  return [...(store.core?.transcript || [])].reverse()
    .filter((e) => e.role === 'user' && !seen.has(e.text) && seen.add(e.text))
    .slice(0, 6);
}

/**
 * Each section: setup(content) builds any persistent parts (e.g. an input
 * that must survive refreshes) and returns update(), which re-renders only
 * when the section's signature (sig) changes.
 */
const SECTIONS = [
  {
    key: 'tasks', title: 'Current tasks', icon: 'tasks',
    badge: () => pending().length || '',
    sig: () => JSON.stringify(store.tasks) + halfMinute(),
    setup(content, { openView }) {
      const input = h('input.input', { type: 'text', placeholder: 'Add a task…', 'aria-label': 'New task', maxlength: '280' });
      const add = async () => {
        const text = input.value.trim();
        if (!text) return;
        try { await post('tasks', { text }); input.value = ''; }
        catch (err) { toast(err.message, 'error'); }
      };
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
      const list = h('div');
      content.append(
        h('div.inline-add', {}, input, iconButton('plus', 'Add task', add)),
        list,
        openView ? h('button.panel-link', { type: 'button', onclick: () => openView('tasks') }, 'All tasks & reminders', icon('send')) : '');
      return () => {
        const items = pending().slice(0, 5);
        list.replaceChildren(items.length
          ? h('div.feed', {}, items.map((task) => taskRow(task)))
          : h('p.feed-empty', {}, store.tasks ? 'Nothing pending. Try “remind me to stretch in 20 minutes”.' : 'Loading…'));
      };
    },
  },
  {
    key: 'commands', title: 'Recent commands', icon: 'history',
    sig: () => JSON.stringify(commands()),
    setup: (content) => () => {
      const items = commands();
      content.replaceChildren(items.length
        ? h('div.feed', {}, items.map((entry) =>
          h('div.feed__item', {},
            h('span.feed__icon', {}, icon('history')),
            h('span.feed__text', {}, entry.text),
            h('button.icon-btn.feed__action', {
              type: 'button', 'aria-label': `Run “${entry.text}” again`, 'data-tip': 'Run again',
              style: { width: '26px', height: '22px' },
              onclick: () => post('command', { text: entry.text }).catch((e) => toast(e.message, 'error')),
            }, icon('replay')))))
        : h('p.feed-empty', {}, 'Commands you give this session appear here.'));
    },
  },
  {
    key: 'notes', title: 'Notifications', icon: 'bell',
    badge: () => notes().length || '',
    sig: () => JSON.stringify(notes()) + halfMinute(),
    setup: (content) => () => {
      const items = notes();
      content.replaceChildren(...(items.length ? [
        h('div.feed', {}, items.map((n) =>
          h('div.feed__item', { dataset: { tone: n.level } },
            h('span.feed__icon', {}, icon(NOTE_ICON[n.level] || 'info')),
            h('span.feed__text', {}, n.text),
            h('time.feed__time', {}, relTime(n.ts))))),
        h('button.panel-link', { type: 'button', onclick: () => post('notifications/clear').catch((e) => toast(e.message, 'error')) }, 'Clear notifications'),
      ] : [h('p.feed-empty', {}, 'No notifications.')]));
    },
  },
  {
    key: 'activity', title: 'AI activity', icon: 'activity',
    sig: () => JSON.stringify(store.core?.activity || []) + halfMinute(),
    setup: (content) => () => {
      const items = [...(store.core?.activity || [])].reverse().slice(0, 12);
      content.replaceChildren(items.length
        ? h('div.feed', {}, items.map((a) =>
          h('div.feed__item', { dataset: { tone: a.kind === 'error' ? 'warn' : 'ok' } },
            h('span.feed__icon', {}, icon(ACTIVITY_ICON[a.kind] || 'activity')),
            h('span.feed__text', {}, a.text),
            h('time.feed__time', {}, relTime(a.ts)))))
        : h('p.feed-empty', {}, 'Nothing yet — Parzival’s actions will be logged here.'));
    },
  },
  {
    key: 'services', title: 'Connected services', icon: 'plug',
    sig: () => JSON.stringify(store.core?.services || []),
    setup: (content) => () => content.replaceChildren(renderServices()),
  },
];

export function mountContext(container, { openView } = {}) {
  const open = loadOpen();

  const nodes = SECTIONS.map((section) => {
    const content = h('div.acc__content');
    const badge = h('span.badge');
    const isOpen = Boolean(open[section.key]);
    const head = h('button.acc__head', { type: 'button', 'aria-expanded': String(isOpen) },
      h('span.acc__icon', {}, icon(section.icon)),
      h('span.acc__title', {}, section.title),
      badge,
      h('span.acc__chev', {}, icon('chevron')));
    const body = h('div.acc__body', {}, h('div.acc__inner', {}, content));
    const root = h('section.acc', { dataset: { open: String(isOpen) } }, head, body);
    head.addEventListener('click', () => {
      const next = root.dataset.open !== 'true';
      root.dataset.open = String(next);
      head.setAttribute('aria-expanded', String(next));
      open[section.key] = next;
      try { localStorage.setItem(OPEN_KEY, JSON.stringify(open)); } catch { /* ignore */ }
    });
    container.append(root);
    return { section, badge, update: section.setup(content, { openView }), sig: null };
  });

  const render = () => {
    for (const node of nodes) {
      const sig = node.section.sig();
      if (sig === node.sig) continue;
      node.sig = sig;
      node.update();
      if (node.section.badge) node.badge.textContent = String(node.section.badge());
    }
  };

  subscribe((s, keys) => { if (keys.some((k) => k === 'core' || k === 'tasks')) render(); });
  setInterval(render, 30_000);   // keep relative times fresh
  render();
}

export function taskRow(task) {
  const due = task.due ? dueLabel(task.due) : null;
  return h('div.task-row', { dataset: { done: String(task.done) } },
    h('button.check', {
      type: 'button', role: 'checkbox', 'aria-checked': String(task.done),
      'aria-label': `Mark “${task.text}” ${task.done ? 'not done' : 'done'}`, onclick: () => toggleTask(task),
    }, icon('check')),
    h('span.task-row__text', {}, task.text),
    due && !task.done ? h('span.due', { dataset: { overdue: String(due.overdue) } }, due.text) : h('span'));
}

export function renderServices() {
  const items = store.core?.services || [];
  if (!items.length) return h('p.feed-empty', {}, 'Waiting for the core…');
  return h('div', {}, items.map((s) =>
    h('div.service', { dataset: { status: s.status } },
      h('span.service__dot', { 'aria-hidden': 'true' }),
      h('span.service__name', {}, s.name),
      h('span.service__detail', {}, s.detail))));
}

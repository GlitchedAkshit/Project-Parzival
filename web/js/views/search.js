// Search across long-term conversation memory, this session and tasks.
// With an empty query it shows the full history (the old History page).
import { h, icon, fmtClock, fmtDay, highlight, debounce } from '../dom.js';
import { api, post } from '../api.js';
import { confirmDialog, toast } from '../ui/feedback.js';

export function createSearchView() {
  const input = h('input.input', {
    type: 'search', placeholder: 'Search conversations and tasks…', 'aria-label': 'Search conversations and tasks',
  });
  const results = h('div', { 'aria-live': 'polite' });
  const el = h('div', {}, h('div.search-box', {}, icon('search'), input), results);

  let seq = 0;
  let shownRevision = null;

  const loading = () => results.replaceChildren(
    ...[0, 1, 2].map((i) => h('div.skeleton', { style: { height: '64px', margin: '12px 0', opacity: String(1 - i * 0.25) } })));

  const failed = (err) => results.replaceChildren(
    h('div.empty-state', {}, h('span.empty-state__icon', {}, icon('warn')),
      h('p.empty-state__title', {}, 'Search is unavailable'), h('p.empty-state__text', {}, err.message)));

  const messageCard = (m, q) => h('article.result.glass-lite', {},
    h('div.result__meta', {},
      h('span', { class: m.role === 'user' ? 'who-user' : 'who-bot' }, m.role === 'user' ? 'You' : 'Parzival'),
      m.ts ? h('time', {}, `${new Date(m.ts * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })} · ${fmtClock(m.ts)}`) : null),
    h('p.result__text', {}, highlight(String(m.content).replace(/^"|"$/g, ''), q)));

  async function search() {
    const q = input.value.trim();
    const mine = ++seq;
    if (!q) return showHistory(true);
    loading();
    try {
      const data = await api(`search?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return;
      const blocks = [];
      if (data.tasks.length) {
        blocks.push(h('h3.section-title', {}, `Tasks · ${data.tasks.length}`));
        blocks.push(...data.tasks.map((t) => h('article.result.glass-lite', {},
          h('div.result__meta', {}, h('span', {}, t.done ? 'Completed task' : t.due ? 'Reminder' : 'Task')),
          h('p.result__text', {}, highlight(t.text, q)))));
      }
      if (data.messages.length) {
        blocks.push(h('h3.section-title', {}, `Conversation · ${data.messages.length}`));
        blocks.push(...data.messages.map((m) => messageCard(m, q)));
      }
      results.replaceChildren(...(blocks.length ? blocks : [
        h('div.empty-state', {}, h('span.empty-state__icon', {}, icon('search')),
          h('p.empty-state__title', {}, `Nothing found for “${q}”`),
          h('p.empty-state__text', {}, 'Search covers Parzival’s long-term memory, this session and your tasks.')),
      ]));
    } catch (err) {
      if (mine === seq) failed(err);
    }
  }

  async function showHistory(force = false, revision = null) {
    if (!force && revision !== null && revision === shownRevision) return;
    const mine = ++seq;
    if (force && shownRevision === null) loading();
    try {
      const { history } = await api('history');
      if (mine !== seq || input.value.trim()) return;
      shownRevision = revision;
      if (!history.length) {
        results.replaceChildren(h('div.empty-state', {}, h('span.empty-state__icon', {}, icon('history')),
          h('p.empty-state__title', {}, 'No conversation history yet'),
          h('p.empty-state__text', {}, 'Conversations with Parzival are remembered across restarts and appear here.')));
        return;
      }
      const days = new Map();
      for (const m of history) {
        const key = m.ts ? fmtDay(m.ts) : 'Earlier';
        if (!days.has(key)) days.set(key, []);
        days.get(key).push(m);
      }
      const blocks = [h('div.section-row', {},
        h('h3.section-title', {}, `Long-term memory · ${history.length} messages`),
        h('button.btn.btn--sm.btn--danger', { type: 'button', onclick: clearMemory }, icon('trash'), 'Clear memory'))];
      for (const [day, items] of [...days.entries()].reverse()) {
        blocks.push(h('h4.history-day', {}, day));
        blocks.push(...items.map((m) => messageCard(m, '')));
      }
      results.replaceChildren(...blocks);
    } catch (err) {
      if (mine === seq) failed(err);
    }
  }

  async function clearMemory() {
    const ok = await confirmDialog({
      title: 'Clear long-term memory?',
      message: 'Parzival will forget every past conversation. This can’t be undone.',
      confirmLabel: 'Clear memory', danger: true,
    });
    if (!ok) return;
    try { await post('history/clear'); toast('Memory cleared.', 'ok'); showHistory(true); }
    catch (err) { toast(err.message, 'error'); }
  }

  input.addEventListener('input', debounce(search, 180));

  return {
    el,
    focus: () => input.focus(),
    onShow: (store) => { if (!input.value.trim()) showHistory(true, store.memory?.revision ?? null); },
    update: (store, keys) => {
      if (keys.includes('memory') && !input.value.trim()) showHistory(false, store.memory?.revision ?? null);
    },
  };
}

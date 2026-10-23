// D. Conversation panel - session transcript with live speech, streaming
// replies, processing indicator, copy/replay actions and the composer.
import { h, icon, iconButton, fmtClock } from '../dom.js';
import { post } from '../api.js';
import { store, subscribe } from '../store.js';
import { toast } from './feedback.js';

const SUGGESTIONS = [
  'What time is it?',
  'Turn on the living room light',
  'Remind me to stretch in 20 minutes',
  'What are my tasks?',
];

export function initConversation() {
  const list = document.getElementById('messages');
  const subtitle = document.getElementById('conv-subtitle');
  const form = document.getElementById('composer');
  const input = document.getElementById('composer-input');
  const send = document.getElementById('composer-send');
  const clearBtn = document.getElementById('conv-clear');

  send.append(icon('send'));
  clearBtn.append(icon('trash'));

  const rendered = new Map();     // transcript id -> <li>
  let coreId = null;
  let liveEl = null;
  let liveKey = '';
  let emptyEl = null;
  let history = [];               // typed commands, for ArrowUp recall
  let historyIdx = -1;

  // ---- composer -------------------------------------------------------------
  const sync = () => { send.disabled = !input.value.trim(); };
  input.addEventListener('input', sync);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp' && (!input.value || historyIdx >= 0) && history.length) {
      e.preventDefault();
      historyIdx = Math.min(history.length - 1, historyIdx + 1);
      input.value = history[history.length - 1 - historyIdx];
      sync();
    } else if (e.key === 'ArrowDown' && historyIdx >= 0) {
      e.preventDefault();
      historyIdx -= 1;
      input.value = historyIdx >= 0 ? history[history.length - 1 - historyIdx] : '';
      sync();
    } else if (e.key === 'Escape' && input.value) {
      e.stopPropagation();
      input.value = '';
      sync();
    }
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    historyIdx = -1;
    history.push(text);
    sync();
    try {
      await post('command', { text });
    } catch (err) {
      toast(err.message, 'error');
      input.value = text;
      sync();
    }
  });

  clearBtn.addEventListener('click', async () => {
    try {
      await post('transcript/clear');
      toast('Conversation log cleared. Parzival’s long-term memory is kept.', 'ok');
    } catch (err) { toast(err.message, 'error'); }
  });

  // ---- rendering -------------------------------------------------------------
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 90;
  const scrollToEnd = (smooth) => list.scrollTo({ top: list.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });

  const copyButton = (text) => {
    const btn = iconButton('copy', 'Copy response', async () => {
      try {
        await navigator.clipboard.writeText(text);
        btn.replaceChildren(icon('check'));
        btn.classList.add('is-done');
        setTimeout(() => { btn.replaceChildren(icon('copy')); btn.classList.remove('is-done'); }, 1600);
      } catch {
        toast("Couldn't copy to the clipboard.", 'error');
      }
    });
    return btn;
  };

  const message = (entry, { live = false } = {}) => {
    const isUser = entry.role === 'user';
    const actions = h('div.msg__actions');
    if (!live) {
      if (isUser) actions.append(iconButton('replay', 'Run again', () => post('command', { text: entry.text }).catch((e) => toast(e.message, 'error'))));
      else actions.append(copyButton(entry.text));
    }
    return h(`li.msg.msg--${isUser ? 'user' : 'assistant'}${live ? '.msg--live' : ''}`, {},
      h('div.msg__meta', {},
        isUser ? null : h('span.msg__dot', { 'aria-hidden': 'true' }),
        h('span.msg__who', {}, isUser ? 'You' : 'Parzival'),
        entry.ts ? h('time.msg__time', {}, fmtClock(entry.ts)) : null,
        actions),
      h('div.msg__body', {}, entry.body || entry.text));
  };

  const liveContent = (core) => {
    if (!core) return null;
    if (core.status === 'listening') {
      return { key: `l:${core.partial}`, role: 'user', body: [core.partial || 'Listening', h('span.caret')] };
    }
    if (core.reply_draft) {
      return { key: `d:${core.reply_draft}`, role: 'assistant', body: [core.reply_draft, h('span.caret')], stream: true };
    }
    if (core.status === 'thinking') {
      return {
        key: 'thinking', role: 'assistant',
        body: h('span.processing', {}, h('span.processing__dots', { 'aria-hidden': 'true' }, h('i'), h('i'), h('i')),
          h('span.shimmer-text', {}, 'Processing')),
      };
    }
    return null;
  };

  const showEmpty = (show) => {
    if (show && !emptyEl) {
      emptyEl = h('li.conv-empty', {},
        h('div.conv-empty__mark', { 'aria-hidden': 'true' }),
        h('p.conv-empty__title', {}, 'Ready when you are'),
        h('p.conv-empty__text', {}, `Say “${(store.core?.wake_word || 'Parzival').replace(/^./, (c) => c.toUpperCase())}”, press the hotkey, or type a command below.`),
        h('div.suggestions', {}, SUGGESTIONS.map((text, i) =>
          h('button.chip', { type: 'button', style: { '--i': i }, onclick: () => post('command', { text }).catch((e) => toast(e.message, 'error')) }, text))));
      list.append(emptyEl);
    } else if (!show && emptyEl) {
      emptyEl.remove();
      emptyEl = null;
    }
  };

  const render = () => {
    const core = store.core;
    if (!core) return;
    const stick = nearBottom();

    if (core.core_id !== coreId) {
      coreId = core.core_id;
      for (const el of rendered.values()) el.remove();
      rendered.clear();
    }

    const transcript = core.transcript || [];
    const ids = new Set(transcript.map((e) => e.id));
    for (const [id, el] of rendered) {
      if (!ids.has(id)) { el.remove(); rendered.delete(id); }
    }
    let added = false;
    const liveKind = liveEl?.dataset.kind || '';
    for (const entry of transcript) {
      if (rendered.has(entry.id)) continue;
      const el = message(entry);
      // The live bubble the user was watching becomes this message - don't re-animate it
      if ((entry.role === 'assistant' && liveKind === 'assistant:s') || (entry.role === 'user' && liveKind === 'user:l')) {
        el.style.animation = 'none';
      }
      rendered.set(entry.id, el);
      list.insertBefore(el, liveEl && liveEl.isConnected ? liveEl : null);
      added = true;
    }

    // Live line (partial speech / streaming reply / processing)
    const live = liveContent(core);
    const key = live ? `${live.role}|${live.key}` : '';
    if (key !== liveKey) {
      const sameKind = live && liveEl && liveEl.dataset.kind === `${live.role}:${live.stream ? 's' : live.key[0]}`;
      if (live && sameKind) {
        liveEl.querySelector('.msg__body').replaceChildren(...[live.body].flat());
      } else {
        liveEl?.remove();
        liveEl = null;
        if (live) {
          liveEl = message({ role: live.role, body: live.body }, { live: true });
          liveEl.dataset.kind = `${live.role}:${live.stream ? 's' : live.key[0]}`;
          list.append(liveEl);
        }
      }
      liveKey = key;
    }

    showEmpty(!transcript.length && !live);
    const n = transcript.length;
    subtitle.textContent = n ? `This session · ${n} message${n === 1 ? '' : 's'}` : 'This session';
    clearBtn.disabled = !n;

    if (added || stick) scrollToEnd(added);
  };

  subscribe((s, keys) => { if (keys.includes('core')) render(); });
  render();

  return { focus: () => input.focus() };
}

// Toasts and the confirm dialog.
import { h, icon } from '../dom.js';

const TONE_ICON = { ok: 'check', error: 'error', warn: 'warn', info: 'info' };

export function toast(message, tone = 'info', ms = 3800) {
  const root = document.getElementById('toasts');
  const el = h('div.toast', { role: tone === 'error' ? 'alert' : 'status', dataset: { tone } },
    h('span.toast__icon', {}, icon(TONE_ICON[tone] || 'info')),
    h('span', {}, message));
  root.append(el);
  while (root.children.length > 4) root.firstElementChild.remove();
  setTimeout(() => {
    el.classList.add('is-leaving');
    el.addEventListener('animationend', () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 400);   // in case animations are disabled
  }, ms);
}

/** Glass confirm dialog. Resolves true/false. Esc cancels, focus is trapped. */
export function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const cancel = h('button.btn', { type: 'button' }, 'Cancel');
    const ok = h(`button.btn.${danger ? 'btn--danger' : 'btn--primary'}`, { type: 'button' }, confirmLabel);
    const dialog = h('div.modal.glass.glass--deep', {
      role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'modal-title', 'aria-describedby': 'modal-text',
    },
      h('h2.modal__title', { id: 'modal-title' }, title),
      h('p.modal__text', { id: 'modal-text' }, message),
      h('div.modal__actions', {}, cancel, ok));
    const backdrop = h('div.modal-backdrop', {}, dialog);

    const close = (value) => {
      document.removeEventListener('keydown', onKey, true);
      backdrop.remove();
      previous?.focus?.();
      resolve(value);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(false); }
      if (e.key === 'Tab') {
        e.preventDefault();
        (document.activeElement === ok ? cancel : ok).focus();
      }
    };
    cancel.addEventListener('click', () => close(false));
    ok.addEventListener('click', () => close(true));
    backdrop.addEventListener('pointerdown', (e) => { if (e.target === backdrop) close(false); });
    document.addEventListener('keydown', onKey, true);
    document.getElementById('modal-root').append(backdrop);
    (danger ? cancel : ok).focus();
  });
}

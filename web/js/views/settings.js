// Settings: the same settings.json fields as before (validated server-side
// by backend/settings_schema.py), plus interface preferences stored locally.
import { h, icon } from '../dom.js';
import { api, post } from '../api.js';
import { store } from '../store.js';
import { toast } from '../ui/feedback.js';
import { getPrefs, setPrefs } from '../prefs.js';

export function createSettingsView() {
  const form = h('form.settings-form', { novalidate: true });
  const status = h('span.settings-status', { role: 'status' });
  const saveBtn = h('button.btn', { type: 'submit' }, 'Save');
  const restartBtn = h('button.btn.btn--primary', { type: 'button' }, icon('replay'), 'Save & restart Parzival');
  const inputs = {};
  let waitingFor = null;   // core_id we're restarting away from

  const say = (text, tone = '') => { status.textContent = text; status.dataset.tone = tone; };

  const control = (field) => {
    const id = `set-${field.key}`;
    if (field.kind === 'bool') {
      const sw = h('button.switch', { type: 'button', role: 'switch', id, 'aria-checked': String(Boolean(field.value)) });
      sw.addEventListener('click', () => sw.setAttribute('aria-checked', String(sw.getAttribute('aria-checked') !== 'true')));
      inputs[field.key] = { get: () => sw.getAttribute('aria-checked') === 'true' };
      return sw;
    }
    const attrs = { id };
    if (field.kind === 'secret') {
      const input = h('input.input', { ...attrs, type: 'password', autocomplete: 'off',
        placeholder: field.has_value ? '•••••• saved — leave blank to keep' : 'Not set' });
      inputs[field.key] = { get: () => input.value };
      return input;
    }
    const value = Array.isArray(field.value) ? field.value.join(', ') : String(field.value ?? '');
    const input = h('input.input', { ...attrs, type: field.kind === 'int' || field.kind === 'float' ? 'number' : 'text',
      step: field.kind === 'float' ? '0.1' : field.kind === 'int' ? '1' : undefined, value });
    inputs[field.key] = { get: () => input.value };
    return input;
  };

  const interfaceGroup = () => {
    const prefs = getPrefs();
    const effects = h('button.switch', { type: 'button', role: 'switch', id: 'pref-effects', 'aria-checked': String(prefs.effects === 'reduced') });
    effects.addEventListener('click', () => {
      const reduced = effects.getAttribute('aria-checked') !== 'true';
      effects.setAttribute('aria-checked', String(reduced));
      setPrefs({ effects: reduced ? 'reduced' : 'full' });
    });
    return h('section.settings-group.glass-lite', {},
      h('h3.section-title', {}, 'Interface'),
      h('div.setting', {},
        h('label.setting__label', { for: 'pref-effects' }, 'Reduce visual effects',
          h('small.setting__help', {}, 'Calmer motion, no bloom or parallax. Also follows your system’s reduced-motion setting.')),
        h('div.setting__control', {}, effects)));
  };

  async function load() {
    form.replaceChildren(...[0, 1].map(() => h('div.skeleton', { style: { height: '160px', marginBottom: '12px' } })));
    try {
      const { sections } = await api('settings');
      form.replaceChildren(
        interfaceGroup(),
        ...sections.map((section) => h('section.settings-group.glass-lite', {},
          h('h3.section-title', {}, section.title),
          ...section.fields.map((field) => h('div.setting', {},
            h('label.setting__label', { for: `set-${field.key}` }, field.label),
            h('div.setting__control', {}, control(field)))))),
        h('div.settings-actions', {}, saveBtn, restartBtn, status));
    } catch (err) {
      form.replaceChildren(h('div.empty-state', {}, h('span.empty-state__icon', {}, icon('warn')),
        h('p.empty-state__title', {}, 'Couldn’t load settings'), h('p.empty-state__text', {}, err.message)));
    }
  }

  async function save(restart) {
    const values = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.get()]));
    saveBtn.disabled = restartBtn.disabled = true;
    say(restart ? 'Saving and restarting…' : 'Saving…', 'busy');
    try {
      await post('settings', { values, restart });
      if (restart) {
        waitingFor = store.core?.core_id ?? null;
        say('Restarting Parzival with the new settings…', 'busy');
      } else {
        say('Saved. Voice and model changes apply after a restart.', 'ok');
        saveBtn.disabled = restartBtn.disabled = false;
      }
    } catch (err) {
      say(err.message, 'error');
      saveBtn.disabled = restartBtn.disabled = false;
    }
  }

  form.addEventListener('submit', (e) => { e.preventDefault(); save(false); });
  restartBtn.addEventListener('click', () => save(true));

  return {
    el: h('div', {}, form),
    onShow: () => { if (!waitingFor) load(); },
    update: (s, keys) => {
      if (!waitingFor || !keys.includes('core')) return;
      const core = s.core;
      if (core && core.core_id !== waitingFor && !core.restarting && core.status !== 'loading') {
        waitingFor = null;
        say('Restarted with the new settings.', 'ok');
        toast('Parzival restarted with the new settings.', 'ok');
        saveBtn.disabled = restartBtn.disabled = false;
        load().then(() => say('Restarted with the new settings.', 'ok'));
      }
    },
  };
}

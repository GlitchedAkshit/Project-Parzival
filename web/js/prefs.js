// Interface preferences (this device only).
const KEY = 'parzival.prefs';
const listeners = new Set();

export function getPrefs() {
  try { return { effects: 'full', ...JSON.parse(localStorage.getItem(KEY) || '{}') }; }
  catch { return { effects: 'full' }; }
}

export function setPrefs(patch) {
  const prefs = { ...getPrefs(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* storage unavailable */ }
  applyPrefs(prefs);
  for (const fn of listeners) fn(prefs);
}

export function applyPrefs(prefs = getPrefs()) {
  document.documentElement.dataset.effects = prefs.effects === 'reduced' ? 'reduced' : 'full';
}

export function onPrefsChange(fn) {
  listeners.add(fn);
}

// Minimal observable store. The server pushes state; UI modules subscribe
// and update only the parts of the DOM whose data changed.

const listeners = new Set();

export const store = {
  core: null,          // ParzivalCore snapshot (status, transcript, activity, services, ...)
  devices: null,       // { source, devices }
  tasks: null,         // [task]
  metrics: null,       // { cpu, memory, uptime, ... } or nulls
  memory: null,        // { revision, count }
  link: 'connecting',  // connecting / online / offline
  view: 'assistant',   // dock selection
};

// High-frequency values read by animation loops - deliberately NOT routed
// through subscribers (they'd fire 30x/second).
export const live = {
  level: 0,            // microphone level 0..1 (only while listening)
  levelAt: 0,
};

export function update(patch) {
  Object.assign(store, patch);
  const keys = Object.keys(patch);
  for (const fn of listeners) {
    try { fn(store, keys); } catch (err) { console.error('[store] listener failed', err); }
  }
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The visual state the AI core should show. */
export function visualState() {
  const core = store.core;
  if (store.link === 'offline') return 'error';
  if (!core || core.restarting) return 'loading';
  return core.status || 'idle';
}

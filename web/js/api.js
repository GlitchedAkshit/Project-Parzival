// Talks to the local Parzival server (backend/web_server.py).
// The per-launch session token arrives in the URL fragment (#token=...),
// is kept in sessionStorage, and is sent with every API call.

const TOKEN_KEY = 'parzival.session';

function readToken() {
  const match = location.hash.match(/token=([^&]+)/);
  if (match) {
    try { sessionStorage.setItem(TOKEN_KEY, match[1]); } catch { /* storage unavailable */ }
    history.replaceState(null, '', location.pathname + location.search);
    return match[1];
  }
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

export const token = readToken();

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`/api/${path}`, {
      method,
      headers: {
        'X-Parzival-Token': token,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach Parzival's core.");
  }
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, res.status);
  return data;
}

export const post = (path, body = {}) => api(path, { method: 'POST', body });

/**
 * Opens the live event stream. `handlers` maps event names
 * (state, level, metrics, devices, tasks, memory) to callbacks, plus
 * `link(status)` for connection changes. Reconnects with backoff.
 */
export function connectEvents(handlers) {
  let source = null;
  let attempt = 0;
  let closed = false;

  const open = () => {
    source = new EventSource(`/api/events?token=${encodeURIComponent(token)}`);
    source.onopen = () => { attempt = 0; handlers.link?.('online'); };
    source.onerror = () => {
      handlers.link?.('offline');
      source.close();
      if (!closed) setTimeout(open, Math.min(6000, 500 * 2 ** attempt++));
    };
    for (const type of ['state', 'level', 'metrics', 'devices', 'tasks', 'memory']) {
      source.addEventListener(type, (e) => {
        try { handlers[type]?.(JSON.parse(e.data)); } catch (err) { console.error(`[events] ${type}`, err); }
      });
    }
  };

  open();
  return () => { closed = true; source?.close(); };
}

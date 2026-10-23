// Smart home: the same devices Parzival controls by voice - simulated ones,
// or your real devices (TV, plugs, lights, AC, speakers) through Home
// Assistant. Tiles update in place as state changes; sliders are debounced
// and changes are shown optimistically. Includes guided Android / Google TV
// pairing (the TV shows a code; the connection is encrypted end to end).
import { h, icon } from '../dom.js';
import { post } from '../api.js';
import { toast } from '../ui/feedback.js';

const KIND_ICON = { light: 'bulb', switch: 'plug', fan: 'fan', thermostat: 'thermo', lock: 'lock', tv: 'tv', speaker: 'speaker' };
const HOLD_MS = 1600;
const F = { PAUSE: 1, VOLUME_SET: 4, MUTE: 8, PREV: 16, NEXT: 32, PLAY: 16384, VOLUME_STEP: 1024 };

export function createHomeView() {
  const source = h('span.source-pill');
  const addBtn = h('button.btn.btn--sm', { type: 'button', hidden: true }, icon('plus'), 'Add a TV');
  const notice = h('div');
  const pairing = createPairing(() => { addBtn.hidden = false; });
  const grid = h('div.device-grid');
  const tiles = new Map();
  const pendingUntil = new Map();   // name -> timestamp; ignore stale pushes meanwhile
  let lastStore = null;

  addBtn.addEventListener('click', () => {
    addBtn.hidden = true;
    pairing.open();
    if (lastStore) render(lastStore);   // hide the empty state's own "Add your TV" button
  });

  const send = async (name, updates, hold = true) => {
    if (hold) pendingUntil.set(name, Date.now() + HOLD_MS);
    try { await post('devices', { name, updates }); }
    catch (err) { pendingUntil.delete(name); toast(err.message, 'error'); }
  };

  // ---- generic tiles (lights, plugs, fans, thermostats, locks) ----------------------
  const createTile = (name, device) => {
    if (device.type === 'tv' || device.type === 'speaker') return createMediaTile(name, device, send, pendingUntil);
    const kind = device.type;
    const status = h('p.device__status');
    const tile = { kind, device, status, el: null, sw: null, range: null, value: null, timer: 0, dragging: false };

    const head = h('div.device__head', {},
      h('span.device__icon', {}, icon(KIND_ICON[kind] || 'plug')),
      h('div', {}, h('p.device__name', {}, name), status));

    if (['light', 'fan', 'switch', 'lock'].includes(kind)) {
      tile.sw = h('button.switch', { type: 'button', role: 'switch', 'aria-label': kind === 'lock' ? `${name} locked` : `${name} power` });
      tile.sw.addEventListener('click', () => {
        const checked = tile.sw.getAttribute('aria-checked') !== 'true';
        const updates = kind === 'lock' ? { locked: checked } : { on: checked };
        tile.device = { ...tile.device, ...updates };
        paint(tile);
        send(name, updates);
      });
      head.append(tile.sw);
    }

    const parts = [head];
    if (kind === 'light' || kind === 'thermostat') {
      const key = kind === 'light' ? 'brightness' : 'temperature';
      const [min, max] = kind === 'light' ? [0, 100] : [device.min ?? 50, device.max ?? 90];
      tile.range = h('input.range', { type: 'range', min: String(min), max: String(max), step: '1', 'aria-label': kind === 'light' ? `${name} brightness` : `${name} temperature` });
      tile.value = h('span.device__value');
      tile.key = key;
      tile.range.addEventListener('pointerdown', () => { tile.dragging = true; });
      addEventListener('pointerup', () => { tile.dragging = false; });
      tile.range.addEventListener('input', () => {
        const v = Number(tile.range.value);
        tile.device = { ...tile.device, [key]: v, ...(kind === 'light' ? { on: v > 0 } : {}) };
        paint(tile, { keepSlider: true });
        clearTimeout(tile.timer);
        pendingUntil.set(name, Date.now() + HOLD_MS);
        tile.timer = setTimeout(() => send(name, { [key]: v }), 220);
      });
      parts.push(h('div.device__slider', {}, tile.range, tile.value));
    }

    tile.el = h('article.device.glass-lite', { dataset: { kind } }, ...parts);
    tile.update = (d) => { tile.device = d; paint(tile); };
    paint(tile);
    return tile;
  };

  const paint = (tile, { keepSlider = false } = {}) => {
    const d = tile.device;
    let active = false, status = '';
    const unit = d.unit === 'C' ? '°C' : '°F';
    if (tile.kind === 'lock') { active = Boolean(d.locked); status = d.locked ? 'Locked' : 'Unlocked'; }
    else if (tile.kind === 'thermostat') { status = `Set to ${d.temperature}${unit}`; }
    else {
      active = Boolean(d.on);
      status = tile.kind === 'light' ? `${d.on ? 'On' : 'Off'} · ${d.brightness ?? 100}%` : d.on ? 'On' : 'Off';
    }
    tile.el.dataset.active = String(active);
    tile.status.textContent = status;
    if (tile.sw) tile.sw.setAttribute('aria-checked', String(tile.kind === 'lock' ? Boolean(d.locked) : Boolean(d.on)));
    if (tile.range) {
      const v = Number(d[tile.key] ?? (tile.kind === 'light' ? 100 : 70));
      if (!keepSlider && !tile.dragging) tile.range.value = String(v);
      const min = Number(tile.range.min), max = Number(tile.range.max);
      tile.range.style.setProperty('--p', `${((Number(tile.range.value) - min) / (max - min)) * 100}%`);
      tile.value.textContent = tile.kind === 'light' ? `${tile.range.value}%` : `${tile.range.value}${unit}`;
    }
  };

  // ---- Home Assistant status notices ----------------------------------------------------
  const renderNotice = (store) => {
    const ha = store.core?.ha_status;
    const card = (glyph, tone, title, text, action) => h('div.ha-notice.glass-lite', { dataset: { tone } },
      h('span.ha-notice__icon', {}, icon(glyph)),
      h('div', {}, h('p.ha-notice__title', {}, title), h('p.ha-notice__text', {}, text)), action || '');
    let el = null;
    if (ha === 'off') {
      el = card('plug', 'info', 'Connect your real devices',
        'Parzival controls your TV, smart plugs, lights and AC through Home Assistant, which runs on this PC and talks to your devices over your own Wi-Fi. Add your Home Assistant access token in Settings to begin.');
    } else if (ha === 'unreachable') {
      el = card('warn', 'warn', 'Home Assistant isn’t running',
        'Start it (Docker Desktop → homeassistant, or run “docker start homeassistant”) and your real devices will appear here within a few seconds. Showing simulated devices meanwhile.');
    } else if (ha === 'insecure') {
      el = card('shield', 'error', 'Blocked for your safety',
        'The Home Assistant address uses plain http on another machine, so your access token would cross the network unencrypted. Use an https:// address in Settings, or run Home Assistant on this PC.');
    }
    notice.replaceChildren(...(el ? [el] : []));
  };

  const render = (store) => {
    lastStore = store;
    const data = store.devices;
    const haConnected = data?.source === 'home-assistant';
    const haStatus = store.core?.ha_status;
    source.dataset.tone = haConnected ? 'ok' : haStatus === 'unreachable' || haStatus === 'insecure' ? 'warn' : '';
    source.replaceChildren(icon(haConnected ? 'shield' : 'home'),
      haConnected ? 'Home Assistant · local' : haStatus === 'unreachable' ? 'Simulated · HA not running' : 'Simulated devices');
    if (!pairing.isOpen()) addBtn.hidden = !haConnected;
    renderNotice(store);

    if (!data) {
      grid.replaceChildren(...[0, 1, 2].map(() => h('div.skeleton', { style: { height: '120px' } })));
      return;
    }
    const devices = data.devices || {};
    const names = Object.keys(devices);
    if (!names.length) {
      tiles.clear();
      grid.replaceChildren(h('div.empty-state', { style: { gridColumn: '1 / -1' } }, h('span.empty-state__icon', {}, icon('tv')),
        h('p.empty-state__title', {}, haConnected ? 'No devices in Home Assistant yet' : 'No devices found'),
        h('p.empty-state__text', {}, haConnected ? 'Add your TV with the button above. Plugs, lights and ACs added in Home Assistant appear here automatically.' : 'devices.json is empty.'),
        haConnected && !pairing.isOpen() ? h('button.btn.btn--primary', { type: 'button', onclick: () => addBtn.click(), style: { marginTop: '12px' } }, icon('tv'), 'Add your TV') : ''));
      return;
    }
    const signature = names.map((n) => `${n}:${devices[n].type}`).join('|');
    if (signature !== grid.dataset.sig) {
      grid.dataset.sig = signature;
      tiles.clear();
      // TVs and speakers first - they're the richest controls
      const ordered = [...names].sort((a, b) => Number(!['tv', 'speaker'].includes(devices[a].type)) - Number(!['tv', 'speaker'].includes(devices[b].type)));
      grid.replaceChildren(...ordered.map((name, i) => {
        const tile = createTile(name, devices[name]);
        tile.el.classList.add('reveal');
        tile.el.style.setProperty('--i', i);
        tiles.set(name, tile);
        return tile.el;
      }));
      return;
    }
    for (const name of names) {
      if ((pendingUntil.get(name) || 0) > Date.now()) continue;   // optimistic value still showing
      tiles.get(name)?.update(devices[name]);
    }
  };

  return {
    el: h('div', {},
      notice,
      h('div.section-row', {}, h('h3.section-title', {}, 'Devices'), h('div.section-row__actions', {}, addBtn, source)),
      pairing.el,
      grid,
      h('p.hint-line', {}, 'Voice: ', h('q', {}, 'turn on the TV'), ' · ', h('q', {}, 'open YouTube on the TV'), ' · ',
        h('q', {}, 'mute the TV'), ' · ', h('q', {}, 'turn off all the lights'), ' · ', h('q', {}, 'set the thermostat to 24'))),
    onShow: render,
    onHide: () => pairing.close(true),
    update: (store, keys) => { if (keys.includes('devices') || keys.includes('core')) render(store); },
  };
}

// ---------------------------------------------------------------------------------
// TV / speaker tile
// ---------------------------------------------------------------------------------
function createMediaTile(name, device, send, pendingUntil) {
  const status = h('p.device__status');
  const power = h('button.switch', { type: 'button', role: 'switch', 'aria-label': `${name} power` });
  const muteBtn = h('button.icon-btn', { type: 'button', 'aria-label': 'Mute', 'data-tip': 'Mute' });
  const range = h('input.range', { type: 'range', min: '0', max: '100', step: '1', 'aria-label': `${name} volume` });
  const value = h('span.device__value');
  const volRow = h('div.device__slider.device__slider--volume', {}, muteBtn, range, value);
  const keyBtn = (glyph, label, command) => h('button.ctrl.ctrl--sm', { type: 'button', 'aria-label': label, onclick: () => send(name, { command }, false) }, icon(glyph), h('span', {}, label));
  const transport = h('div.control-row.tv-transport', {},
    keyBtn('prev', 'Previous', 'previous'), keyBtn('playPause', 'Play / pause', 'play_pause'), keyBtn('next', 'Next', 'next'));
  const keys = h('div.control-row.tv-keys', {}, keyBtn('home', 'Home', 'home'), keyBtn('back', 'Back', 'back'),
    keyBtn('volDown', 'Vol −', 'volume_down'), keyBtn('volUp', 'Vol +', 'volume_up'));
  const apps = h('div.tv-apps');
  const el = h('article.device.device--media.glass-lite', { dataset: { kind: device.type } },
    h('div.device__head', {},
      h('span.device__icon', {}, icon(device.type === 'speaker' ? 'speaker' : 'tv')),
      h('div', {}, h('p.device__name', {}, name), status),
      power),
    volRow, transport, keys, apps);

  let timer = 0, dragging = false, appsSig = '';
  const tile = { el, device };

  power.addEventListener('click', () => {
    const on = power.getAttribute('aria-checked') !== 'true';
    tile.device = { ...tile.device, on };
    paint();
    send(name, { on });
  });
  muteBtn.addEventListener('click', () => {
    const muted = !tile.device.muted;
    tile.device = { ...tile.device, muted };
    paint();
    send(name, { muted });
  });
  range.addEventListener('pointerdown', () => { dragging = true; });
  addEventListener('pointerup', () => { dragging = false; });
  range.addEventListener('input', () => {
    tile.device = { ...tile.device, volume: Number(range.value) };
    paint(true);
    clearTimeout(timer);
    pendingUntil.set(name, Date.now() + HOLD_MS);
    timer = setTimeout(() => send(name, { volume: Number(range.value) }), 250);
  });

  function paint(keepSlider = false) {
    const d = tile.device;
    const has = (bit) => (d.features & bit) === bit;
    const on = Boolean(d.on);
    el.dataset.active = String(on);
    el.dataset.off = String(!on);
    status.textContent = !d.available ? 'Unavailable · the TV may be fully powered down'
      : on ? ['On', d.source, d.title].filter(Boolean).join(' · ') : 'Off · standby';
    power.setAttribute('aria-checked', String(on));
    power.disabled = !d.available;

    const volume = d.volume;
    volRow.hidden = !(has(F.VOLUME_SET) || has(F.MUTE)) ;
    range.hidden = !has(F.VOLUME_SET) || volume === null || volume === undefined;
    if (!keepSlider && !dragging && volume != null) range.value = String(volume);
    range.style.setProperty('--p', `${range.value}%`);
    value.textContent = d.muted ? 'Muted' : volume != null ? `${range.value}%` : '';
    muteBtn.replaceChildren(icon(d.muted ? 'volMute' : 'volUp'));
    muteBtn.setAttribute('aria-pressed', String(Boolean(d.muted)));
    muteBtn.hidden = !has(F.MUTE);

    transport.hidden = !(has(F.PAUSE) || has(F.PLAY) || has(F.NEXT));
    keys.hidden = !d.remote;
    for (const ctrl of el.querySelectorAll('button.ctrl, .tv-apps .chip, .range, .icon-btn')) ctrl.disabled = !on;

    const appList = [...new Set([...(d.apps || []), ...(d.sources || [])])].slice(0, 12);
    const sig = appList.join('|');
    if (sig !== appsSig) {
      appsSig = sig;
      apps.replaceChildren(...appList.map((app) =>
        h('button.chip', { type: 'button', disabled: !on, onclick: () => send(name, { app }, false) }, app)));
    }
    apps.hidden = !appList.length;
  }

  tile.update = (d) => { tile.device = d; paint(); };
  paint();
  return tile;
}

// ---------------------------------------------------------------------------------
// Guided Android / Google TV pairing
// ---------------------------------------------------------------------------------
function createPairing(onClose) {
  const body = h('div.pair__body');
  const el = h('section.pair.glass-lite', { hidden: true, 'aria-live': 'polite' },
    h('div.pair__head', {},
      h('span.pair__icon', {}, icon('tv')),
      h('div', {}, h('p.pair__title', {}, 'Add your Android / Google TV'),
        h('p.pair__sub', {}, 'Pairing is encrypted and stays on your Wi-Fi. Your TV will show a code to confirm it’s you.')),
      h('button.icon-btn', { type: 'button', 'aria-label': 'Cancel', 'data-tip': 'Cancel', onclick: () => close() }, icon('close'))),
    body);
  let flowId = null;
  let open = false;

  const msg = (text, tone = '') => h('p.pair__msg', { dataset: { tone } }, text);

  function stepFind(message = '', tone = '') {
    const ip = h('input.input', { type: 'text', inputmode: 'decimal', placeholder: 'TV IP address, e.g. 192.168.1.20', 'aria-label': 'TV IP address' });
    const connect = h('button.btn.btn--primary', { type: 'button' }, 'Connect');
    const find = h('button.btn', { type: 'button' }, icon('radar'), 'Find my TV');
    const found = h('div.pair__found');
    connect.addEventListener('click', () => startPair(ip.value.trim()));
    ip.addEventListener('keydown', (e) => { if (e.key === 'Enter') startPair(ip.value.trim()); });
    find.addEventListener('click', async () => {
      find.disabled = true;
      found.replaceChildren(msg('Looking for TVs on your Wi-Fi…', 'busy'));
      try {
        const { tvs } = await post('ha/discover-tvs');
        found.replaceChildren(...(tvs.length
          ? [msg(`Found ${tvs.length === 1 ? 'a TV' : `${tvs.length} TVs`} - choose yours:`),
             h('div.pair__choices', {}, tvs.map((tv) => h('button.chip', { type: 'button', onclick: () => startPair(tv.host) }, icon('tv'), tv.name ? `${tv.name} (${tv.host})` : tv.host)))]
          : [msg('No TV answered. Make sure it’s switched on (not just in standby) and on the same Wi-Fi, or type its IP address - it’s under Settings → Network & Internet on the TV.', 'warn')]));
      } catch (err) {
        found.replaceChildren(msg(err.message, 'error'));
      } finally {
        find.disabled = false;
      }
    });
    body.replaceChildren(
      h('ol.pair__steps', {}, h('li', {}, 'Switch the TV on and connect it to the same Wi-Fi as this PC.'),
        h('li', {}, 'Find it automatically, or type its IP address.'), h('li', {}, 'Type the code that appears on the TV.')),
      h('div.pair__row', {}, find, ip, connect),
      found,
      message ? msg(message, tone) : '');
    setTimeout(() => find.focus(), 0);
  }

  async function startPair(host) {
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return stepFind('Enter an IP address like 192.168.1.20.', 'error');
    body.replaceChildren(msg(`Contacting the TV at ${host}… watch your TV screen.`, 'busy'));
    try {
      handle(await post('ha/pair', { host }));
    } catch (err) {
      stepFind(err.message, 'error');
    }
  }

  function stepPin(name, message = '') {
    const pin = h('input.input.pair__pin', { type: 'text', maxlength: '8', autocomplete: 'one-time-code', placeholder: 'CODE', 'aria-label': 'Code shown on the TV' });
    const pair = h('button.btn.btn--primary', { type: 'button' }, 'Pair');
    const submit = async () => {
      if (!pin.value.trim()) return;
      pair.disabled = true;
      try { handle(await post('ha/pair/pin', { flow_id: flowId, pin: pin.value.trim() })); }
      catch (err) { stepPin(name, err.message); }
    };
    pair.addEventListener('click', submit);
    pin.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    pin.addEventListener('input', () => { pin.value = pin.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); });
    body.replaceChildren(
      msg(`A code is now showing on ${name}. Type it here:`),
      h('div.pair__row', {}, pin, pair),
      message ? msg(message, 'error') : '');
    setTimeout(() => pin.focus(), 0);
  }

  function handle(result) {
    if (result.status === 'need_pin') { flowId = result.flow_id; stepPin(result.name, result.message); return; }
    if (result.status === 'paired' || result.status === 'done') {
      flowId = null;
      toast(result.status === 'paired' ? `${result.name} is connected. Try “turn on the TV”.` : result.message, 'ok', 5000);
      close(true);
      return;
    }
    stepFind(result.message || 'Pairing didn’t complete. Try again.', 'error');
  }

  function close(silent = false) {
    if (flowId) post('ha/pair/cancel', { flow_id: flowId }).catch(() => {});
    flowId = null;
    if (!open) return;
    open = false;
    el.hidden = true;
    onClose?.();
    if (!silent) toast('Pairing cancelled.', 'info', 2000);
  }

  return {
    el,
    isOpen: () => open,
    open() { open = true; el.hidden = false; stepFind(); },
    close,
  };
}

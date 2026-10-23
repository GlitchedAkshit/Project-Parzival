// System information + PC controls. Metrics are real (Win32 API via the
// backend); if the platform can't provide them the cards say so.
import { h, icon, fmtDuration } from '../dom.js';
import { post } from '../api.js';
import { renderServices } from '../ui/context.js';
import { confirmDialog, toast } from '../ui/feedback.js';

const NS = 'http://www.w3.org/2000/svg';

export function createSystemView() {
  const cpuValue = h('div.metric__value');
  const cpuSpark = sparkline();
  const memValue = h('div.metric__value');
  const memDetail = h('p.metric__detail');
  const memBar = h('div.metric__bar', {}, h('i'));
  const upValue = h('div.metric__value');
  const upDetail = h('p.metric__detail', {}, 'Since Windows last started');
  const services = h('div.service-list');

  const metrics = h('div.metric-grid', {},
    h('div.metric.glass-lite', {}, h('p.metric__label', {}, 'Processor'), cpuValue, cpuSpark.svg),
    h('div.metric.glass-lite', {}, h('p.metric__label', {}, 'Memory'), memValue, memDetail, memBar),
    h('div.metric.glass-lite', {}, h('p.metric__label', {}, 'Uptime'), upValue, upDetail));

  const ctrl = (glyph, label, action, opts = {}) => {
    const btn = h(`button.ctrl${opts.danger ? '.ctrl--danger' : ''}`, { type: 'button', 'aria-label': label }, icon(glyph), h('span', {}, label));
    btn.addEventListener('click', async () => {
      if (opts.confirm && !(await confirmDialog(opts.confirm))) return;
      btn.disabled = true;
      try {
        const res = await post('system', { action });
        toast(res.message, res.ok ? 'ok' : 'error', action === 'screenshot' ? 6000 : 3000);
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        btn.disabled = false;
      }
    });
    return btn;
  };

  const controls = h('div.control-groups', {},
    h('div.control-group.glass-lite', {}, h('p.control-group__title', {}, 'Volume'),
      h('div.control-row', {}, ctrl('volDown', 'Down', 'volume_down'), ctrl('volMute', 'Mute', 'mute'), ctrl('volUp', 'Up', 'volume_up'))),
    h('div.control-group.glass-lite', {}, h('p.control-group__title', {}, 'Media'),
      h('div.control-row', {}, ctrl('prev', 'Previous', 'previous_track'), ctrl('playPause', 'Play / pause', 'play_pause'), ctrl('next', 'Next', 'next_track'))),
    h('div.control-group.glass-lite', {}, h('p.control-group__title', {}, 'Capture & security'),
      h('div.control-row', {},
        ctrl('camera', 'Screenshot', 'screenshot'),
        ctrl('lock', 'Lock PC', 'lock_pc', {
          danger: true,
          confirm: { title: 'Lock this PC?', message: 'Windows will lock immediately. You’ll need your password or PIN to get back in.', confirmLabel: 'Lock now', danger: true },
        }))));

  const el = h('div', {},
    h('h3.section-title', {}, 'Live metrics'), metrics,
    h('h3.section-title', {}, 'Controls'), controls,
    h('h3.section-title', {}, 'Engines & services'), h('div.glass-lite', { style: { padding: '8px 10px' } }, services));

  const render = (store) => {
    const m = store.metrics;
    const hist = (store.metricsHistory || []).map((x) => x.cpu).filter((v) => v !== null && v !== undefined);
    cpuValue.replaceChildren(...(m?.cpu != null ? [String(Math.round(m.cpu)), h('small', {}, '%')] : ['—']));
    cpuSpark.set(hist);
    if (m?.memory != null) {
      memValue.replaceChildren(String(m.memory), h('small', {}, '%'));
      memDetail.textContent = `${m.memory_used_gb} GB of ${m.memory_total_gb} GB in use`;
      memBar.firstChild.style.setProperty('--v', (m.memory / 100).toFixed(3));
    } else {
      memValue.textContent = '—';
      memDetail.textContent = 'Not available on this platform';
    }
    upValue.textContent = m?.uptime != null ? fmtDuration(m.uptime) : '—';
    services.replaceChildren(renderServices());
  };

  return {
    el,
    onShow: render,
    update: (store, keys) => { if (keys.includes('metrics') || keys.includes('core')) render(store); },
  };
}

function sparkline() {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'metric__spark');
  svg.setAttribute('viewBox', '0 0 100 40');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `<defs><linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="rgb(63,224,255)" stop-opacity="0.28"/>
      <stop offset="1" stop-color="rgb(63,224,255)" stop-opacity="0"/></linearGradient></defs>
    <polygon/><polyline/>`;
  const [poly, line] = [svg.querySelector('polygon'), svg.querySelector('polyline')];
  return {
    svg,
    set(values) {
      if (values.length < 2) { line.setAttribute('points', ''); poly.setAttribute('points', ''); return; }
      const n = values.length;
      const pts = values.map((v, i) => `${((i / (n - 1)) * 100).toFixed(2)},${(38 - (Math.min(100, v) / 100) * 36).toFixed(2)}`);
      line.setAttribute('points', pts.join(' '));
      poly.setAttribute('points', `0,40 ${pts.join(' ')} 100,40`);
    },
  };
}

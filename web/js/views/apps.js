// Application launchers - each one is a real action in backend/system_control.py
// (and works by voice too: "open notepad").
import { h, icon } from '../dom.js';
import { post } from '../api.js';
import { toast } from '../ui/feedback.js';

const APPS = [
  { action: 'open_browser', name: 'Web browser', sub: 'Your default browser', icon: 'globe', say: 'open browser' },
  { action: 'open_explorer', name: 'File Explorer', sub: 'Browse your files', icon: 'folder', say: 'open file explorer' },
  { action: 'open_notepad', name: 'Notepad', sub: 'Quick plain-text notes', icon: 'note', say: 'open notepad' },
  { action: 'open_calculator', name: 'Calculator', sub: 'Windows Calculator', icon: 'calculator', say: 'open calculator' },
  { action: 'open_task_manager', name: 'Task Manager', sub: 'Processes & performance', icon: 'gauge', say: 'open task manager' },
  { action: 'open_settings', name: 'Windows Settings', sub: 'System preferences', icon: 'gear', say: 'open settings' },
];

export function createAppsView() {
  const tiles = APPS.map((app) => {
    const tile = h('button.app-tile.glass-lite.is-interactive', { type: 'button', 'aria-label': `Open ${app.name}` },
      h('span.app-tile__icon', {}, icon(app.icon)),
      h('span.app-tile__name', {}, app.name),
      h('span.app-tile__sub', {}, `Say “${app.say}”`));
    tile.addEventListener('click', async () => {
      tile.classList.add('is-busy');
      try {
        const res = await post('system', { action: app.action });
        toast(res.message, res.ok ? 'ok' : 'error');
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        tile.classList.remove('is-busy');
      }
    });
    return tile;
  });

  return {
    el: h('div', {},
      h('div.app-grid', {}, tiles),
      h('p.hint-line', {}, 'Applications open on this PC. Parzival only launches the apps listed here.')),
  };
}

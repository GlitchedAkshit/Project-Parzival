// Line icon set (24px grid, 1.6 stroke, currentColor). Hand-drawn for
// Parzival - no emoji, no icon font.
const PATHS = {
  core: '<circle cx="12" cy="12" r="2.6"/><circle cx="12" cy="12" r="6.6" stroke-dasharray="3.2 2.4"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.3-4.3"/>',
  apps: '<rect x="4" y="4" width="6.6" height="6.6" rx="1.9"/><rect x="13.4" y="4" width="6.6" height="6.6" rx="1.9"/><rect x="4" y="13.4" width="6.6" height="6.6" rx="1.9"/><rect x="13.4" y="13.4" width="6.6" height="6.6" rx="1.9"/>',
  system: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 9.8h4v4.4h-4z"/><path d="M10 3.6v3M14 3.6v3M10 17.4v3M14 17.4v3M3.6 10h3M3.6 14h3M17.4 10h3M17.4 14h3"/>',
  tasks: '<path d="M10 6.5h10M10 12h10M10 17.5h10"/><path d="m3.8 6.4 1.5 1.5 2.4-2.6M3.8 11.9l1.5 1.5 2.4-2.6"/><circle cx="5.6" cy="17.5" r="1.3"/>',
  home: '<path d="M3.8 11.2 12 4.3l8.2 6.9"/><path d="M6.2 9.6v9.9h11.6V9.6"/><path d="M10 19.5v-5h4v5"/>',
  settings: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  activity: '<path d="M3 12h4l2.5-6 5 12 2.5-6h4"/>',
  mic: '<rect x="9" y="3.4" width="6" height="11.2" rx="3"/><path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0M12 17.9v2.7"/>',
  micOff: '<path d="M15 10.3V6.4a3 3 0 0 0-5.6-1.5M9 9v2.6a3 3 0 0 0 4.6 2.5"/><path d="M5.6 11.4a6.4 6.4 0 0 0 10.3 5.1M18.3 13a6.3 6.3 0 0 0 .1-1.6M12 17.9v2.7M4 4l16 16"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="2.4"/>',
  send: '<path d="M5 12h13.5M13.2 6.4 18.8 12l-5.6 5.6"/>',
  copy: '<rect x="8.6" y="8.6" width="11" height="11" rx="2.3"/><path d="M15.4 5.6V5a1.6 1.6 0 0 0-1.6-1.6H6A2.6 2.6 0 0 0 3.4 6v7.8A1.6 1.6 0 0 0 5 15.4h.6"/>',
  check: '<path d="m5 12.6 4.2 4.2L19 7"/>',
  trash: '<path d="M4.5 7h15M10 7V5.2h4V7M6.6 7l.9 12.6h9l.9-12.6"/>',
  close: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  plus: '<path d="M12 5.5v13M5.5 12h13"/>',
  chevron: '<path d="m7.5 10 4.5 4.5 4.5-4.5"/>',
  bell: '<path d="M6.4 16.6V11a5.6 5.6 0 0 1 11.2 0v5.6l1.6 1.6H4.8z"/><path d="M10 20.6h4"/>',
  plug: '<path d="M9 3.6v3.6M15 3.6v3.6"/><path d="M6.4 7.2h11.2v3.4a5.6 5.6 0 0 1-11.2 0z"/><path d="M12 16.2v4.2"/>',
  clock: '<circle cx="12" cy="12" r="8.2"/><path d="M12 7.6V12l3 1.9"/>',
  history: '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4.4v3.9h3.9"/><path d="M12 8v4.2l2.8 1.8"/>',
  replay: '<path d="M4.6 12a7.4 7.4 0 1 0 2.2-5.2"/><path d="M4.6 4.6v3.6h3.6"/><path d="m10.4 9.4 4 2.6-4 2.6z"/>',
  volUp: '<path d="M3.8 9.6h3.4L12 5.6v12.8l-4.8-4H3.8z"/><path d="M15.6 9a4 4 0 0 1 0 6M18.2 6.4a7.6 7.6 0 0 1 0 11.2"/>',
  volDown: '<path d="M3.8 9.6h3.4L12 5.6v12.8l-4.8-4H3.8z"/><path d="M15.8 9a4 4 0 0 1 0 6"/>',
  volMute: '<path d="M3.8 9.6h3.4L12 5.6v12.8l-4.8-4H3.8z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>',
  playPause: '<path d="M4.6 6.2v11.6l7.2-5.8z"/><path d="M15.6 6.6v10.8M19.6 6.6v10.8"/>',
  next: '<path d="M5.6 6.4v11.2l8.2-5.6z"/><path d="M17.8 6.4v11.2"/>',
  prev: '<path d="M18.4 6.4v11.2l-8.2-5.6z"/><path d="M6.2 6.4v11.2"/>',
  camera: '<path d="M3.8 8.4h3.4l1.8-2.6h6l1.8 2.6h3.4v10.4H3.8z"/><circle cx="12" cy="13.4" r="3.3"/>',
  lock: '<rect x="5.4" y="10.6" width="13.2" height="9.6" rx="2.3"/><path d="M8.4 10.6V8.2a3.6 3.6 0 0 1 7.2 0v2.4"/>',
  unlock: '<rect x="5.4" y="10.6" width="13.2" height="9.6" rx="2.3"/><path d="M8.4 10.6V8.2a3.6 3.6 0 0 1 6.9-1.4"/>',
  globe: '<circle cx="12" cy="12" r="8.4"/><path d="M3.6 12h16.8M12 3.6c2.5 2.4 3.8 5.2 3.8 8.4s-1.3 6-3.8 8.4c-2.5-2.4-3.8-5.2-3.8-8.4S9.5 6 12 3.6z"/>',
  folder: '<path d="M3.6 7.6a2 2 0 0 1 2-2h4.1l2 2.2h6.7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5.6a2 2 0 0 1-2-2z"/>',
  note: '<path d="M6.4 3.6h8.2L18 7v13.4H6.4z"/><path d="M14.4 3.6V7.2H18M9 11.6h6M9 15.2h6"/>',
  calculator: '<rect x="5.4" y="3.4" width="13.2" height="17.2" rx="2.3"/><path d="M8.4 7.4h7.2"/><path d="M8.8 11.6h.01M12 11.6h.01M15.2 11.6h.01M8.8 15.4h.01M12 15.4h.01M15.2 15.4h.01" stroke-width="2.4"/>',
  gauge: '<path d="M4.4 16.6a8 8 0 1 1 15.2 0"/><path d="m12 14 3.6-4.2"/><circle cx="12" cy="14.2" r="1.3"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3.4v2.4M12 18.2v2.4M3.4 12h2.4M18.2 12h2.4M5.9 5.9l1.7 1.7M16.4 16.4l1.7 1.7M5.9 18.1l1.7-1.7M16.4 7.6l1.7-1.7"/>',
  bulb: '<path d="M9 17.6h6M10 20.6h4"/><path d="M12 3.4a5.6 5.6 0 0 0-3.3 10.1c.8.6 1.3 1.4 1.3 2.3v1.8h4v-1.8c0-.9.5-1.7 1.3-2.3A5.6 5.6 0 0 0 12 3.4z"/>',
  fan: '<circle cx="12" cy="12" r="1.7"/><path d="M12 10.3c0-3.4.9-6.5 3-6.5 2.5 0 2.7 4.3-1.4 6.7M13.7 12c3.4 0 6.5.9 6.5 3 0 2.5-4.3 2.7-6.7-1.4M12 13.7c0 3.4-.9 6.5-3 6.5-2.5 0-2.7-4.3 1.4-6.7M10.3 12c-3.4 0-6.5-.9-6.5-3 0-2.5 4.3-2.7 6.7 1.4"/>',
  thermo: '<path d="M10 14.4V5.2a2 2 0 0 1 4 0v9.2a3.6 3.6 0 1 1-4 0z"/><path d="M12 9.2v6.6"/>',
  info: '<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5.2M12 7.9h.01"/>',
  warn: '<path d="M12 4.2 21 19.6H3z"/><path d="M12 10v4.2M12 16.9h.01"/>',
  error: '<circle cx="12" cy="12" r="8.4"/><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6"/>',
  wave: '<path d="M3.5 12h2M7 8.5v7M10.5 5.5v13M14 8v8M17.5 10v4M20.5 12h0"/>',
  keyboard: '<rect x="3" y="6.5" width="18" height="11" rx="2.2"/><path d="M7 10h.01M10.3 10h.01M13.6 10h.01M17 10h.01M7.5 14h9"/>',
  tv: '<rect x="3" y="4.8" width="18" height="12.4" rx="2.2"/><path d="M8.6 20.6h6.8M12 17.2v3.4"/>',
  speaker: '<rect x="6" y="3.4" width="12" height="17.2" rx="2.6"/><circle cx="12" cy="14.2" r="3"/><path d="M12 7.4h.01" stroke-width="2.4"/>',
  back: '<path d="M10 6.4 4.4 12l5.6 5.6M5 12h14.6"/>',
  shield: '<path d="M12 3.4 19 6v5.6c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6z"/><path d="m9 12.2 2.1 2.1L15.2 10"/>',
  radar: '<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="4.4"/><path d="M12 12 18 6"/>',
};

const NS = 'http://www.w3.org/2000/svg';

export function icon(name, cls = '') {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.innerHTML = PATHS[name] || PATHS.info;
  return svg;
}

// B + C. The AI core and the voice interface beneath it.
import { h, icon } from '../dom.js';
import { post } from '../api.js';
import { store, live, subscribe, visualState } from '../store.js';
import { CoreRenderer } from '../fx/core.js';
import { VoiceWave } from '../fx/waveform.js';
import { toast } from './feedback.js';

const STATE_RGB = {
  loading: [120, 170, 215],
  idle: [63, 224, 255],
  listening: [44, 228, 255],
  thinking: [118, 168, 255],
  speaking: [62, 236, 236],
  error: [255, 181, 71],
};

const LABEL = {
  loading: 'INITIALIZING',
  idle: 'SYSTEM ONLINE',
  listening: 'LISTENING',
  thinking: 'PROCESSING',
  speaking: 'SPEAKING',
  error: 'CORE OFFLINE',
};

const prettyHotkey = (spec) => String(spec || '').split('+').map((p) => p.trim()).filter(Boolean)
  .map((p) => (p.length === 1 ? p.toUpperCase() : p[0].toUpperCase() + p.slice(1)));

export function initStage() {
  const app = document.getElementById('app');
  const coreEl = document.getElementById('core');
  const canvas = document.getElementById('core-canvas');
  const stateEl = document.getElementById('core-state');
  const subEl = document.getElementById('core-sub');
  const transcriptEl = document.getElementById('voice-transcript');
  const mic = document.getElementById('mic-btn');
  const micIcon = mic.querySelector('.mic__icon');
  const wake = document.getElementById('wake-toggle');
  const hint = document.getElementById('voice-hint');

  const getLevel = () => (performance.now() - live.levelAt < 400 ? live.level : 0);
  const renderer = new CoreRenderer(canvas, {
    getLevel,
    onFrameRate: () => console.info('[core] frame rate low - switched the core to its lighter rendering mode'),
  });
  const wave = new VoiceWave(document.getElementById('voice-wave'), { getLevel });

  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const applyMotion = () => renderer.setReducedMotion(motionQuery.matches || document.documentElement.dataset.effects === 'reduced');
  motionQuery.addEventListener('change', applyMotion);
  applyMotion();
  renderer.start();

  // ---- interactions ------------------------------------------------------------
  const micAction = async () => {
    const core = store.core;
    if (!core || store.link !== 'online') return toast("Parzival's core isn't connected yet.", 'warn');
    if (!core.mic_ready) {
      return toast(core.voice_error ? 'Microphone unavailable — you can still type commands.' : 'The microphone is still starting up.', 'warn');
    }
    renderer.nudge();
    try {
      if (core.status === 'thinking' || core.status === 'speaking') await post('interrupt');
      else await post('activate');     // starts listening, or cancels if already listening
    } catch (err) { toast(err.message, 'error'); }
  };
  mic.addEventListener('click', micAction);
  canvas.addEventListener('click', micAction);   // tap the core to talk

  wake.addEventListener('click', async () => {
    const next = wake.getAttribute('aria-checked') !== 'true';
    wake.setAttribute('aria-checked', String(next));       // optimistic
    try { await post('wake', { enabled: next }); }
    catch (err) { wake.setAttribute('aria-checked', String(!next)); toast(err.message, 'error'); }
  });

  // ---- render -----------------------------------------------------------------
  let lastVisual = null;
  let lastMicState = null;

  const render = () => {
    const core = store.core;
    const visual = visualState();
    const rgb = STATE_RGB[visual] || STATE_RGB.idle;

    if (visual !== lastVisual) {
      renderer.setState(visual);
      document.documentElement.style.setProperty('--state-rgb', rgb.join(', '));
      app.dataset.visual = visual;
      stateEl.textContent = core?.restarting ? 'RESTARTING' : LABEL[visual];
      stateEl.classList.remove('is-swapping');
      void stateEl.offsetWidth;                       // restart the swap animation
      stateEl.classList.add('is-swapping');
      lastVisual = visual;
    }
    wave.setMode(['listening', 'speaking', 'thinking'].includes(visual) ? visual : 'idle', rgb);

    // Sub-line under the state label
    let sub = '';
    if (store.link === 'offline') sub = 'Connection to the core was lost — reconnecting';
    else if (!core || visual === 'loading') sub = core?.restarting ? 'Applying new settings…' : 'Bringing systems online…';
    else if (visual === 'listening') sub = 'Go ahead — I’m listening';
    else if (visual === 'thinking') sub = 'Working on it';
    else if (visual === 'speaking') sub = 'Press Esc or the stop button to interrupt';
    else if (core.llm_status === 'offline') sub = 'Conversation offline — start Ollama · commands still work';
    else if (core.llm_status === 'missing-model') sub = `Run “ollama pull ${core.llm_model}” to enable conversation`;
    else if (core.llm_status === 'checking') sub = `Loading ${core.llm_model}…`;
    else sub = `All systems nominal · ${core.llm_model}`;
    if (subEl.textContent !== sub) subEl.textContent = sub;

    // Live transcription line
    let line, isHint = false;
    if (!core) { line = ''; }
    else if (visual === 'listening') line = [core.partial || 'Listening…', h('span.caret')];
    else if ((visual === 'thinking' || visual === 'speaking') && core.reply_draft) line = tail(core.reply_draft, 150);
    else if (visual === 'speaking') line = tail(core.last_reply || '', 150);
    else if (visual === 'thinking') line = core.last_heard ? `“${tail(core.last_heard, 110)}”` : '';
    else if (!core.mic_ready && core.status !== 'loading') { line = 'Microphone unavailable — type your command in the conversation panel.'; isHint = true; }
    else {
      isHint = true;
      const wakeWord = (core.wake_word || 'Parzival').replace(/^./, (c) => c.toUpperCase());
      line = core.wake_enabled && core.wake_phrases?.length
        ? `Say “${wakeWord}”, or tap the microphone`
        : 'Tap the microphone or press the hotkey to talk';
    }
    const lineKey = Array.isArray(line) ? `L${line[0]}` : String(line);
    if (transcriptEl.dataset.key !== lineKey) {
      transcriptEl.dataset.key = lineKey;
      transcriptEl.replaceChildren(...[line].flat());
      transcriptEl.classList.toggle('is-hint', isHint);
    }

    // Microphone button
    let micState = 'ready', label = 'Start listening', glyph = 'mic';
    if (!core || core.status === 'loading' || store.link !== 'online') { micState = 'loading'; label = 'Starting up'; }
    else if (!core.mic_ready) { micState = 'unavailable'; label = 'Microphone unavailable'; glyph = 'micOff'; }
    else if (core.status === 'listening') { micState = 'listening'; label = 'Stop listening'; }
    else if (core.status === 'thinking' || core.status === 'speaking') { micState = 'busy'; label = 'Stop Parzival'; glyph = 'stop'; }
    if (micState !== lastMicState) {
      mic.dataset.state = micState;
      mic.setAttribute('aria-label', label);
      mic.disabled = micState === 'loading';
      mic.setAttribute('aria-pressed', String(micState === 'listening'));
      micIcon.replaceChildren(icon(glyph));
      lastMicState = micState;
    }

    // Wake word switch + hotkey hint
    const wakeAvailable = Boolean(core?.wake_phrases?.length);
    wake.disabled = !wakeAvailable || store.link !== 'online';
    wake.setAttribute('aria-checked', String(Boolean(core?.wake_enabled && wakeAvailable)));
    wake.title = wakeAvailable ? 'Listen for the wake word' : 'Wake word unavailable';

    const keys = core && !core.hotkey_error ? prettyHotkey(core.hotkey) : [];
    const hintKey = keys.join('+') + (core?.hotkey_error || '');
    if (hint.dataset.key !== hintKey) {
      hint.dataset.key = hintKey;
      hint.replaceChildren(...(keys.length
        ? [...keys.map((k) => h('kbd', {}, k)), h('span', {}, 'push to talk')]
        : core?.hotkey_error ? [h('span', {}, 'Hotkey unavailable — change it in Settings')] : []));
    }
  };

  subscribe((s, keys) => { if (keys.some((k) => k === 'core' || k === 'link')) render(); });
  render();

  return {
    renderer,
    setEffects: applyMotion,
    elements: { app, coreEl },
  };
}

function tail(text, max) {
  if (text.length <= max) return text;
  const cut = text.slice(text.length - max);
  return '…' + cut.slice(cut.indexOf(' ') + 1);
}

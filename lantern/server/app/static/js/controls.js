import {$} from './dom.js';
import {getJson, postJson} from './api.js';
import {state, saveRange} from './state.js';

export async function renderControls(onRangeChange) {
  const cfg = await getJson('/api/config');
  state.config = cfg;
  const ui = cfg.ui || {};
  if (!localStorage.getItem('lantern.graphRangeSeconds')) state.graphRangeSeconds = ui.defaultGraphRangeSeconds || 86400;
  const freq = await getJson('/api/update-frequency');
  $('currentFrequency').textContent = `Current: ${freq.seconds} s`;
  const ub = $('updateButtons'); ub.innerHTML = '';
  (ui.allowedUpdateFrequencySeconds || [2,10,60,120]).forEach(sec => {
    const b = document.createElement('button'); b.textContent = `${sec} s`; if (sec === freq.seconds) b.classList.add('active');
    b.addEventListener('click', async () => { await postJson('/api/update-frequency', {seconds: sec}); await renderControls(onRangeChange); });
    ub.appendChild(b);
  });
  const rb = $('rangeButtons'); rb.innerHTML = '';
  (ui.graphRanges || []).forEach(r => {
    const b = document.createElement('button'); b.textContent = r.label; if (Number(r.seconds) === Number(state.graphRangeSeconds)) b.classList.add('active');
    b.addEventListener('click', () => { state.graphRangeSeconds = Number(r.seconds); saveRange(); renderControls(onRangeChange); onRangeChange(); });
    rb.appendChild(b);
  });
}

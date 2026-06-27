import {$} from './dom.js';
import {renderControls} from './controls.js';
import {refreshAll, refreshGraphs, wireTableControls} from './refresh.js';

function tickClock() { $('clock').textContent = new Date().toLocaleString(); }

async function main() {
  tickClock(); setInterval(tickClock, 1000);
  wireTableControls();
  await renderControls(refreshGraphs);
  await refreshAll();
  setInterval(refreshAll, 10000);
}

main().catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin', `<pre style="color:red">${err}</pre>`);
});

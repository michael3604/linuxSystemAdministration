import {$} from './dom.js';
import {isoDateTime} from './format.js';
import {renderControls} from './controls.js';
import {refreshAll, refreshGraphs, wireTableControls} from './refresh.js';

function tickClock() { $('clock').textContent = isoDateTime(Date.now() / 1000); }

async function main() {
  tickClock(); setInterval(tickClock, 1000);
  wireTableControls();
  await renderControls(refreshGraphs);
  await refreshAll();
  setInterval(() => refreshAll({preserveScroll: true}), 10000);
}

main().catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin', `<pre style="color:red">${err}</pre>`);
});

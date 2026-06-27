import {$} from './dom.js';
import {getJson} from './api.js';
import {state} from './state.js';
import {renderServiceTable, renderHostTable} from './tables.js';
import {drawServiceGraph} from './serviceGraph.js';
import {renderHostGraphs} from './hostGraph.js';
import {selectedKeys, showAll, hideAll, showProblemsOnly, resetSelection} from './selection.js';

export async function refreshAll() {
  const servicesPayload = await getJson('/api/services');
  state.services = servicesPayload.services || [];
  renderServiceTable($('serviceTable'), state.services, refreshGraphs);
  const hostsPayload = await getJson('/api/hosts');
  renderHostTable($('hostTable'), hostsPayload.hosts || []);
  await refreshGraphs();
  $('lastRefresh').textContent = `Last refresh: ${new Date().toLocaleTimeString()}`;
}

export async function refreshGraphs() {
  const keys = selectedKeys();
  const serviceSeries = await getJson(`/api/service-series?rangeSeconds=${state.graphRangeSeconds}&keys=${encodeURIComponent(keys.join(','))}`);
  drawServiceGraph($('serviceGraph'), serviceSeries, state.graphRangeSeconds);
  const hostSeries = await getJson(`/api/host-series?rangeSeconds=${state.graphRangeSeconds}`);
  renderHostGraphs($('hostGraphs'), hostSeries, state.graphRangeSeconds);
}

export function wireTableControls() {
  $('showAll').addEventListener('click', async () => { showAll(); await refreshAll(); });
  $('hideAll').addEventListener('click', async () => { hideAll(); await refreshAll(); });
  $('showProblems').addEventListener('click', async () => { showProblemsOnly(); await refreshAll(); });
  $('resetSelection').addEventListener('click', async () => { resetSelection(); await refreshAll(); });
}

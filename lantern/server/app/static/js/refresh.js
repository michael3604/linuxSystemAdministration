import {$} from './dom.js';
import {getJson} from './api.js';
import {state} from './state.js';
import {isoDateTime} from './format.js';
import {renderServiceTable, renderHostTable} from './tables.js';
import {drawServiceGraph} from './serviceGraph.js';
import {renderHostGraphs} from './hostGraph.js';
import {selectedKeys, showAll, hideAll, showProblemsOnly, resetSelection} from './selection.js';

function captureTableScroll() {
  const positions = {};
  for (const id of ['serviceTable', 'hostTable']) {
    const wrap = $(id)?.querySelector('.table-scroll');
    if (wrap) positions[id] = wrap.scrollLeft;
  }
  return positions;
}

function restoreTableScroll(positions) {
  for (const [id, left] of Object.entries(positions || {})) {
    const wrap = $(id)?.querySelector('.table-scroll');
    if (wrap) wrap.scrollLeft = left;
  }
}

function shouldPreserveWindowScroll() {
  const active = document.activeElement;
  if (!active || active === document.body || active === document.documentElement) return true;
  // Do not fight explicit user interaction with buttons, checkboxes or form fields.
  return !active.matches('button, input, select, textarea, a[href]');
}

async function runWithOptionalScrollPreservation(preserveScroll, fn) {
  const scrollY = window.scrollY;
  const scrollX = window.scrollX;
  const tableScroll = captureTableScroll();
  const preserveWindow = preserveScroll && shouldPreserveWindowScroll();

  await fn();

  restoreTableScroll(tableScroll);
  if (preserveWindow) {
    requestAnimationFrame(() => {
      restoreTableScroll(tableScroll);
      window.scrollTo(scrollX, scrollY);
    });
  }
}

export async function refreshAll(options = {}) {
  const preserveScroll = Boolean(options.preserveScroll);
  await runWithOptionalScrollPreservation(preserveScroll, async () => {
    const servicesPayload = await getJson('/api/services');
    state.services = servicesPayload.services || [];
    renderServiceTable($('serviceTable'), state.services, refreshGraphs);
    const hostsPayload = await getJson('/api/hosts');
    renderHostTable($('hostTable'), hostsPayload.hosts || []);
    await refreshGraphs({preserveScroll});
    $('lastRefresh').textContent = `Last refresh: ${isoDateTime(Date.now() / 1000)}`;
  });
}

export async function refreshGraphs(options = {}) {
  const preserveScroll = Boolean(options.preserveScroll);
  await runWithOptionalScrollPreservation(preserveScroll, async () => {
    const keys = selectedKeys();
    const serviceSeries = await getJson(`/api/service-series?rangeSeconds=${state.graphRangeSeconds}&keys=${encodeURIComponent(keys.join(','))}`);
    drawServiceGraph($('serviceGraph'), serviceSeries, state.graphRangeSeconds);
    const hostSeries = await getJson(`/api/host-series?rangeSeconds=${state.graphRangeSeconds}`);
    renderHostGraphs($('hostGraphs'), hostSeries, state.graphRangeSeconds);
  });
}

export function wireTableControls() {
  $('showAll').addEventListener('click', async () => { showAll(); await refreshAll({preserveScroll: true}); });
  $('hideAll').addEventListener('click', async () => { hideAll(); await refreshAll({preserveScroll: true}); });
  $('showProblems').addEventListener('click', async () => { showProblemsOnly(); await refreshAll({preserveScroll: true}); });
  $('resetSelection').addEventListener('click', async () => { resetSelection(); await refreshAll({preserveScroll: true}); });
}

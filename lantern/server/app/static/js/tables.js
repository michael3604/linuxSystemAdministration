import {age, esc, valueWithUnit} from './format.js';
import {isSelected, setSelected} from './selection.js';

function badge(status) { return `<span class="badge ${esc(status)}">${esc(status).toUpperCase()}</span>`; }

export function renderServiceTable(container, services, onChange) {
  let html = '<div class="table-scroll"><table class="service-table"><thead><tr>' +
    '<th class="sticky-col sticky-show">Show</th>' +
    '<th class="sticky-col sticky-name">Host / Service</th>' +
    '<th>Type</th><th>Status</th><th>Age</th><th>Value</th><th>Date</th><th>Text</th>' +
    '</tr></thead><tbody>';
  for (const s of services) {
    html += `<tr>` +
      `<td class="sticky-col sticky-show"><input type="checkbox" data-key="${esc(s.key)}" ${isSelected(s) ? 'checked' : ''}></td>` +
      `<td class="sticky-col sticky-name name-cell">${esc(s.hostName)} / ${esc(s.serviceName)}</td>` +
      `<td>${esc(s.sourceType)}</td>` +
      `<td>${badge(s.status)}</td>` +
      `<td>${age(s.ageSeconds)}</td>` +
      `<td class="value">${esc(valueWithUnit(s.value, s.unit))}</td>` +
      `<td>${esc(s.timestamp)}</td>` +
      `<td class="text-cell">${esc(s.text || '')}</td>` +
      `</tr>`;
  }
  html += '</tbody></table></div>';
  container.innerHTML = html;
  container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.addEventListener('change', () => { setSelected(cb.dataset.key, cb.checked); onChange(); }));
}

export function renderHostTable(container, hosts) {
  let html = '<div class="table-scroll"><table class="host-table"><thead><tr>' +
    '<th class="sticky-col sticky-host">Host</th>' +
    '<th>Status</th><th>Age</th><th>CPU</th><th>RAM</th><th>Free RAM</th><th>Temp</th><th>Maint.</th><th>Date</th>' +
    '</tr></thead><tbody>';
  for (const h of hosts) {
    html += `<tr>` +
      `<td class="sticky-col sticky-host name-cell">${esc(h.hostName)}</td>` +
      `<td>${badge(h.status)}</td>` +
      `<td>${age(h.ageSeconds)}</td>` +
      `<td class="value">${valueWithUnit(h.cpuPercent, '%')}</td>` +
      `<td class="value">${valueWithUnit(h.ramPercent, '%')}</td>` +
      `<td class="value">${valueWithUnit(h.ramAvailableMb, 'MB')}</td>` +
      `<td class="value">${valueWithUnit(h.cpuTempC, '°C')}</td>` +
      `<td>${h.maintenanceMode ? 'yes' : 'no'}</td>` +
      `<td>${esc(h.timestamp || '')}</td>` +
      `</tr>`;
  }
  html += '</tbody></table></div>';
  container.innerHTML = html;
}

import {state, saveSelection} from './state.js';
export function isSelected(service) {
  const key = service.key;
  if (Object.prototype.hasOwnProperty.call(state.serviceSelection, key)) return !!state.serviceSelection[key];
  return !!service.defaultVisibleInGraph;
}
export function setSelected(key, value) {
  state.serviceSelection[key] = value;
  saveSelection();
}
export function showAll() { state.services.forEach(s => state.serviceSelection[s.key] = true); saveSelection(); }
export function hideAll() { state.services.forEach(s => state.serviceSelection[s.key] = false); saveSelection(); }
export function showProblemsOnly() { state.services.forEach(s => state.serviceSelection[s.key] = s.stateNumeric > 0); saveSelection(); }
export function resetSelection() { state.serviceSelection = {}; saveSelection(); }
export function selectedKeys() { return state.services.filter(isSelected).map(s => s.key); }

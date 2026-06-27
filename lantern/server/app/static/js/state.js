export const state = {
  config: null,
  graphRangeSeconds: Number(localStorage.getItem('lantern.graphRangeSeconds') || 86400),
  serviceSelection: JSON.parse(localStorage.getItem('lantern.serviceSelection') || '{}'),
  services: [],
};
export function saveSelection() {
  localStorage.setItem('lantern.serviceSelection', JSON.stringify(state.serviceSelection));
}
export function saveRange() {
  localStorage.setItem('lantern.graphRangeSeconds', String(state.graphRangeSeconds));
}

export function age(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  seconds = Math.max(0, Math.floor(seconds));
  if (seconds < 60) return `${seconds} s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}
export function esc(s) {
  return String(s ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
export function valueWithUnit(value, unit) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  const v = Number.isFinite(n) ? (Math.round(n * 100) / 100).toString() : String(value);
  return unit ? `${v} ${unit}` : v;
}
export function timeLabel(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

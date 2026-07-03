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
export function isoDateTime(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    const d = new Date(value * 1000);
    if (!Number.isNaN(d.getTime())) return d.toISOString().replace(/\.000Z$/, 'Z');
  }
  const text = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(text)) return text;
  const normalized = text.endsWith('UTC') ? text.slice(0, -3) + 'Z' : text;
  const d = new Date(normalized);
  if (!Number.isNaN(d.getTime())) return d.toISOString().replace(/\.000Z$/, 'Z');
  return text;
}

export function timeLabel(ts) {
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toISOString().slice(0, 16) + 'Z';
}

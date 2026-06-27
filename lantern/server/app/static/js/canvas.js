export function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(600, rect.width * dpr);
  canvas.height = Math.max(240, canvas.height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {ctx, width: canvas.width / dpr, height: canvas.height / dpr};
}
export function clear(ctx, width, height) {
  ctx.clearRect(0, 0, width, height);
}
export function grid(ctx, x, y, w, h) {
  ctx.strokeStyle = 'rgba(148,163,184,.14)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const yy = y + h * i / 4;
    ctx.beginPath(); ctx.moveTo(x, yy); ctx.lineTo(x+w, yy); ctx.stroke();
  }
  for (let i = 0; i <= 4; i++) {
    const xx = x + w * i / 4;
    ctx.beginPath(); ctx.moveTo(xx, y); ctx.lineTo(xx, y+h); ctx.stroke();
  }
}
export function drawText(ctx, text, x, y, color = '#cbd5e1', size = 12) {
  ctx.fillStyle = color;
  ctx.font = `${size}px system-ui, sans-serif`;
  ctx.fillText(text, x, y);
}
export function statusColor(state) {
  if (state >= 2) return 'rgba(239,68,68,.75)';
  if (state >= 1) return 'rgba(245,158,11,.75)';
  return 'rgba(34,197,94,.65)';
}
export function fillColor(state) {
  if (state >= 2) return 'rgba(239,68,68,.16)';
  if (state >= 1) return 'rgba(245,158,11,.14)';
  return 'rgba(34,197,94,.08)';
}

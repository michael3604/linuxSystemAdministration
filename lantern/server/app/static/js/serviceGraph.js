import {setupCanvas, clear, grid, drawText, statusColor, fillColor} from './canvas.js';
import {timeLabel} from './format.js';

export function drawServiceGraph(canvas, series, rangeSeconds) {
  const {ctx, width, height} = setupCanvas(canvas);
  clear(ctx, width, height);
  const left = 210, right = 20, top = 20, bottom = 26;
  const graphW = width - left - right;
  const services = series.services || [];
  if (!services.length) { drawText(ctx, 'No selected service data', 20, 40); return; }
  const laneH = Math.max(52, (height - top - bottom) / services.length);
  const end = Number(series.rangeEnd || Date.now() / 1000);
  const start = Number(series.rangeStart || (end - rangeSeconds));
  const effectiveRange = Math.max(1, end - start);
  function x(ts) { return left + Math.max(0, Math.min(1, (ts - start) / effectiveRange)) * graphW; }
  ctx.strokeStyle = 'rgba(148,163,184,.14)';
  ctx.lineWidth = 1;
  for (let i=0;i<=4;i++) { const xx = left + graphW*i/4; ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, height-bottom); ctx.stroke(); drawText(ctx, i===4 ? 'now' : timeLabel(start + effectiveRange*i/4), xx-12, height-8, '#9ca3af', 11); }
  services.forEach((svc, idx) => {
    const y0 = top + idx*laneH;
    const laneTop = y0 + 8;
    const laneBottom = y0 + laneH - 8;
    const laneMid = (laneTop + laneBottom) / 2;
    ctx.strokeStyle = 'rgba(148,163,184,.12)'; ctx.beginPath(); ctx.moveTo(left, laneBottom); ctx.lineTo(left+graphW, laneBottom); ctx.stroke();
    drawText(ctx, `${svc.hostName}/${svc.serviceName}`, 12, laneMid-2, '#cbd5e1', 12);
    drawText(ctx, svc.unit || svc.sourceType, 12, laneMid+14, '#9ca3af', 10);
    const pts = (svc.points || []).filter(p => Number.isFinite(Number(p.ts))).sort((a,b) => a.ts-b.ts);
    if (!pts.length) return;
    const numeric = pts.some(p => p.value !== null && p.value !== undefined);
    let min = 0, max = 2;
    if (numeric) {
      const vals = pts.map(p => Number(p.value)).filter(Number.isFinite);
      min = Math.min(...vals); max = Math.max(...vals);
      if (min === max) { min -= 1; max += 1; }
      const pad = (max-min)*0.1; min -= pad; max += pad;
      drawText(ctx, String(Math.round(max*100)/100), left-45, laneTop+8, '#64748b', 10);
      drawText(ctx, String(Math.round(min*100)/100), left-45, laneBottom, '#64748b', 10);
    } else {
      drawText(ctx, '2', left-22, laneTop+8, '#64748b', 10);
      drawText(ctx, '0', left-22, laneBottom, '#64748b', 10);
    }
    function y(p) {
      const v = numeric && p.value !== null && p.value !== undefined ? Number(p.value) : Number(p.stateNumeric ?? 2);
      const t = (v - min) / (max - min);
      return laneBottom - Math.max(0, Math.min(1, t)) * (laneBottom-laneTop);
    }
    // severity fill per segment
    for (let i=0;i<pts.length;i++) {
      const p = pts[i], next = pts[i+1];
      const x1 = x(p.ts), x2 = next ? x(next.ts) : left+graphW;
      ctx.fillStyle = fillColor(p.stateNumeric ?? 0);
      ctx.fillRect(x1, laneTop, Math.max(1, x2-x1), laneBottom-laneTop);
    }
    ctx.strokeStyle = statusColor(Math.max(...pts.map(p => p.stateNumeric ?? 0)));
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach((p, i) => {
      const xx = x(p.ts), yy = y(p);
      if (i === 0) ctx.moveTo(xx, yy);
      else { const prev = pts[i-1]; ctx.lineTo(xx, y(prev)); ctx.lineTo(xx, yy); }
    });
    ctx.lineTo(left+graphW, y(pts[pts.length-1]));
    ctx.stroke();
  });
}

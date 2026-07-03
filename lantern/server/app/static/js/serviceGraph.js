import {setupCanvas, clear, grid, drawText, statusColor, fillColor} from './canvas.js';
import {timeLabel} from './format.js';

export function drawServiceGraph(canvas, series, rangeSeconds) {
  const services = series.services || [];
  const desiredHeight = services.length ? Math.max(260, 20 + 26 + services.length * 56) : 260;
  const {ctx, width, height} = setupCanvas(canvas, desiredHeight);
  clear(ctx, width, height);
  const left = 210, right = 20, top = 20, bottom = 26;
  const graphW = width - left - right;
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
    const numericVals = pts.map(p => Number(p.value)).filter(Number.isFinite);
    const numeric = numericVals.length > 0;
    let min = 0, max = 2;
    function finiteOrNull(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }
    function roundLabel(v) {
      const av = Math.abs(v);
      if (av >= 1000) return String(Math.round(v));
      if (av >= 10) return String(Math.round(v * 10) / 10);
      return String(Math.round(v * 100) / 100);
    }
    if (numeric) {
      const cfgMin = finiteOrNull(svc.graphMin);
      const cfgMax = finiteOrNull(svc.graphMax);
      if (cfgMin !== null && cfgMax !== null && cfgMax > cfgMin) {
        min = cfgMin; max = cfgMax;
      } else if ((svc.unit || '').trim() === '%') {
        min = 0; max = 100;
      } else {
        min = Math.min(...numericVals);
        max = Math.max(...numericVals);
        if (min === max) {
          const span = Math.max(Math.abs(max) * 0.1, 1);
          min -= span; max += span;
        } else {
          const pad = Math.max((max-min)*0.1, 1e-9);
          min -= pad; max += pad;
        }
        // Avoid visually absurd empty axes for sparse data: if all visible values
        // are positive and the lower bound is near zero, pin the bottom to zero.
        if (Math.min(...numericVals) >= 0 && min > 0 && min / max < 0.25) min = 0;
      }
      drawText(ctx, `${roundLabel(max)}${svc.unit ? ' ' + svc.unit : ''}`, left-70, laneTop+8, '#64748b', 10);
      drawText(ctx, `${roundLabel(min)}${svc.unit ? ' ' + svc.unit : ''}`, left-70, laneBottom, '#64748b', 10);
    } else {
      drawText(ctx, 'bad 2', left-46, laneTop+8, '#64748b', 10);
      drawText(ctx, 'good 0', left-55, laneBottom, '#64748b', 10);
    }
    function yValue(v) {
      const t = (v - min) / Math.max(1e-9, (max - min));
      return laneBottom - Math.max(0, Math.min(1, t)) * (laneBottom-laneTop);
    }
    function y(p) {
      if (numeric) {
        const v = finiteOrNull(p.value);
        return yValue(v === null ? numericVals[numericVals.length - 1] : v);
      }
      return yValue(Number(p.stateNumeric ?? 2));
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

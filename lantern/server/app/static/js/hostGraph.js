import {setupCanvas, clear, grid, drawText} from './canvas.js';
import {timeLabel} from './format.js';

function line(ctx, pts, x, y, key) {
  const filtered = pts.filter(p => p[key] !== null && p[key] !== undefined);
  if (!filtered.length) return;
  ctx.beginPath();
  filtered.forEach((p, i) => { const xx=x(p.ts), yy=y(Number(p[key])); if (i===0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy); });
  ctx.stroke();
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function drawAxes(ctx, left, top, w, h, right, height) {
  ctx.save();
  ctx.lineWidth = 1;
  ctx.strokeStyle = 'rgba(148,163,184,.55)';
  ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, top+h); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(left+w, top); ctx.lineTo(left+w, top+h); ctx.stroke();

  ctx.textBaseline = 'middle';
  ctx.textAlign = 'right';
  for (let i=0; i<=4; i++) {
    const value = 100 - i*25;
    const yy = top + h*i/4;
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`${value}%`, left-8, yy);
    ctx.strokeStyle = 'rgba(148,163,184,.55)';
    ctx.beginPath(); ctx.moveTo(left-4, yy); ctx.lineTo(left, yy); ctx.stroke();
  }

  ctx.textAlign = 'left';
  for (let i=0; i<=4; i++) {
    const value = 100 - i*25;
    const yy = top + h*i/4;
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`${value}°C`, left+w+8, yy);
    ctx.strokeStyle = 'rgba(148,163,184,.55)';
    ctx.beginPath(); ctx.moveTo(left+w, yy); ctx.lineTo(left+w+4, yy); ctx.stroke();
  }

  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';
  drawText(ctx, '%', left-28, top-4, '#94a3b8', 11);
  drawText(ctx, '°C', left+w+16, top-4, '#94a3b8', 11);
  ctx.restore();
}

export function renderHostGraphs(container, payload, rangeSeconds) {
  container.innerHTML = '';
  const hosts = payload.hosts || [];
  if (!hosts.length) { container.innerHTML = '<p class="muted">No host graph data yet.</p>'; return; }
  hosts.forEach(host => {
    const wrapper = document.createElement('div');
    wrapper.className = 'host-graph-card';
    wrapper.innerHTML = `<div class="host-graph-title">${host.hostName}</div><canvas height="260"></canvas>`;
    container.appendChild(wrapper);
    const canvas = wrapper.querySelector('canvas');
    const {ctx, width, height} = setupCanvas(canvas, 260);
    clear(ctx, width, height);
    const left=58,right=58,top=20,bottom=28,w=width-left-right,h=height-top-bottom;
    grid(ctx,left,top,w,h);
    drawAxes(ctx,left,top,w,h,right,height);
    const now = Date.now()/1000, start = now-rangeSeconds;
    const pts = (host.points || []).sort((a,b)=>a.ts-b.ts);
    const x = ts => left + clamp((ts-start)/rangeSeconds, 0, 1)*w;
    const yPct = v => top + h - clamp(v, 0, 100)*h/100;
    const yTemp = v => top + h - clamp(v, 0, 100)*h/100;
    // Stale overlay: only mark a host stale if no sample exists for longer than
    // its configured hostStatusMaxAgeSeconds. Do not infer loss from bucket size;
    // short graph ranges can have 1s buckets while clients update every 120s.
    const maxAge = Number(host.maxAgeSeconds || 180);
    function markStale(fromTs, toTs) {
      const x1 = x(fromTs), x2 = x(toTs);
      if (x2 <= x1) return;
      ctx.fillStyle='rgba(239,68,68,.13)'; ctx.fillRect(x1, top, Math.max(1,x2-x1), h);
      ctx.strokeStyle='rgba(239,68,68,.65)'; ctx.beginPath(); ctx.moveTo(x1, top+5); ctx.lineTo(x2, top+5); ctx.stroke();
    }
    if (pts.length) {
      if (pts[0].ts > start + maxAge) markStale(start, pts[0].ts);
      for (let i=0;i<pts.length-1;i++) {
        if (pts[i+1].ts - pts[i].ts > maxAge) markStale(pts[i].ts + maxAge, pts[i+1].ts);
      }
      const last = pts[pts.length-1].ts;
      if (now - last > maxAge) markStale(last + maxAge, now);
    }
    ctx.strokeStyle='#60a5fa'; ctx.lineWidth=2; line(ctx, pts, x, yPct, 'cpuPercent');
    ctx.strokeStyle='#a78bfa'; line(ctx, pts, x, yPct, 'ramPercent');
    ctx.strokeStyle='#f97316'; line(ctx, pts, x, yTemp, 'cpuTempC');
    ctx.setLineDash([6,4]); ctx.strokeStyle='#fde047'; line(ctx, pts.map(p => ({...p, maintenanceMode: p.maintenanceMode ? 100 : 0})), x, yPct, 'maintenanceMode'); ctx.setLineDash([]);
    drawText(ctx,'CPU %',left+8,top+16,'#60a5fa',11); drawText(ctx,'RAM %',left+65,top+16,'#a78bfa',11); drawText(ctx,'Temp °C',left+125,top+16,'#f97316',11); drawText(ctx,'Maintenance',left+190,top+16,'#fde047',11);
    for (let i=0;i<=4;i++) { const xx=left+w*i/4; drawText(ctx, i===4?'now':timeLabel(start+rangeSeconds*i/4), xx-10, height-8, '#9ca3af', 10); }
  });
}

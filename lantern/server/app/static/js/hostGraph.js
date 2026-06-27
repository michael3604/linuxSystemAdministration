import {setupCanvas, clear, grid, drawText} from './canvas.js';
import {timeLabel} from './format.js';

function line(ctx, pts, x, y, key) {
  const filtered = pts.filter(p => p[key] !== null && p[key] !== undefined);
  if (!filtered.length) return;
  ctx.beginPath();
  filtered.forEach((p, i) => { const xx=x(p.ts), yy=y(Number(p[key])); if (i===0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy); });
  ctx.stroke();
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
    const {ctx, width, height} = setupCanvas(canvas);
    clear(ctx, width, height);
    const left=46,right=42,top=16,bottom=28,w=width-left-right,h=height-top-bottom;
    grid(ctx,left,top,w,h);
    const now = Date.now()/1000, start = now-rangeSeconds;
    const pts = (host.points || []).sort((a,b)=>a.ts-b.ts);
    const x = ts => left + Math.max(0, Math.min(1, (ts-start)/rangeSeconds))*w;
    const yPct = v => top + h - Math.max(0, Math.min(100, v))*h/100;
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
    ctx.strokeStyle='#f97316'; line(ctx, pts, x, v => yPct(Math.max(0, Math.min(100, v || 0))), 'cpuTempC');
    ctx.setLineDash([6,4]); ctx.strokeStyle='#fde047'; line(ctx, pts.map(p => ({...p, maintenanceMode: p.maintenanceMode ? 100 : 0})), x, yPct, 'maintenanceMode'); ctx.setLineDash([]);
    drawText(ctx,'CPU %',left+8,top+16,'#60a5fa',11); drawText(ctx,'RAM %',left+65,top+16,'#a78bfa',11); drawText(ctx,'Temp °C',left+125,top+16,'#f97316',11); drawText(ctx,'Maintenance',left+190,top+16,'#fde047',11);
    for (let i=0;i<=4;i++) { const xx=left+w*i/4; drawText(ctx, i===4?'now':timeLabel(start+rangeSeconds*i/4), xx-10, height-8, '#9ca3af', 10); }
  });
}

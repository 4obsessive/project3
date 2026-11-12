// Módulo ÚNICO de mapa: minimapa, partidas e informe usan este mismo render.
// Capas: heat (calor), points (●), crosses (✕), cells (cuadrícula con valor), paths (recorridos), markers, images.
import { api } from './api.js';
import { el, downloadBlob, cssVar } from './util.js';
import { SIDE_COLORS } from './charts.js';

let mapInfoPromise = null;

/** Carga calibración + imagen. Siempre resuelve: si la imagen falla, img = null. */
export function loadMapInfo() {
  if (!mapInfoPromise) {
    mapInfoPromise = (async () => {
      let info;
      try { info = await api.get('/api/map'); } catch (e) { info = { calibration: null, image: '/static/minimap.png', error: e.message }; }
      info.img = await new Promise(resolve => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = info.image + '?v=1';
      });
      return info;
    })();
  }
  return mapInfoPromise;
}
export function resetMapInfo() { mapInfoPromise = null; }

// Mismos tokens que las gráficas (app.css :root); antes había dos verdes/rojos distintos.
export const COLORS = SIDE_COLORS;
const ink = () => cssVar('--mapink', '#000');

export class MapView {
  constructor(container, opts = {}) {
    this.size = opts.size || 760;
    this.grid = opts.grid || 0;
    this.layers = [];
    this.rotate = false;
    this.box = el('div', { class: 'mapbox' });
    this.canvas = el('canvas', { width: this.size, height: this.size, role: 'img', 'aria-label': opts.label || 'Minimapa' });
    this.msg = el('div', { class: 'map-msg', hidden: true });
    this.box.append(this.canvas, this.msg);
    container.append(this.box);
    this.ready = loadMapInfo().then(info => { this.info = info; this.draw(); });
  }

  setLayers(layers, opts = {}) {
    this.layers = layers || [];
    if (opts.grid !== undefined) this.grid = opts.grid;
    if (opts.rotate !== undefined) this.rotate = opts.rotate;
    this.draw();
  }

  /** mundo -> píxel del canvas según la calibración guardada junto a la imagen */
  toPx(x, y) {
    const c = this.info.calibration;
    let u = (x - c.x_min) / (c.x_max - c.x_min);
    let v = (y - c.y_min) / (c.y_max - c.y_min);
    if (c.invert_x) u = 1 - u;
    if (c.invert_y !== false) v = 1 - v;
    if (this.rotate) { u = 1 - u; v = 1 - v; }
    return [u * this.size, v * this.size];
  }

  draw() {
    if (!this.info) return; // se redibuja al terminar de cargar
    const ctx = this.canvas.getContext('2d');
    const S = this.size;
    ctx.clearRect(0, 0, S, S);
    // la imagen es negra semitransparente: siempre sobre fondo claro
    ctx.fillStyle = cssVar('--mapbg', '#ecebe6');
    ctx.fillRect(0, 0, S, S);
    if (this.info.img) {
      ctx.save();
      if (this.rotate) { ctx.translate(S, S); ctx.rotate(Math.PI); }
      ctx.globalAlpha = this.layers.some(L => L.kind === 'heat' && !L.hidden) ? 0.45 : 0.75;
      ctx.drawImage(this.info.img, 0, 0, S, S);
      ctx.restore();
      this.msg.hidden = true;
    } else {
      this.msg.hidden = false;
      this.msg.textContent = 'No se pudo cargar la imagen del minimapa (static/minimap.png). Se dibujan los datos sin fondo.';
    }
    if (!this.info.calibration) {
      this.msg.hidden = false;
      this.msg.textContent = 'Sin calibración del mapa: no se pueden situar los puntos.';
      return;
    }
    if (this.grid) this.drawGrid(ctx);
    for (const L of this.layers) {
      if (L.hidden) continue;
      const fn = { heat: this.drawHeat, points: this.drawPoints, crosses: this.drawCrosses, cells: this.drawCells, paths: this.drawPaths, markers: this.drawMarkers, images: this.drawImages }[L.kind];
      if (fn) fn.call(this, ctx, L);
    }
  }

  drawGrid(ctx) {
    const S = this.size, g = this.grid, step = S / g;
    ctx.save();
    ctx.strokeStyle = 'rgba(0,0,0,.25)'; ctx.lineWidth = 1;
    ctx.fillStyle = 'rgba(0,0,0,.55)'; ctx.font = '12px system-ui';
    for (let i = 1; i < g; i++) {
      ctx.beginPath(); ctx.moveTo(i * step, 0); ctx.lineTo(i * step, S); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * step); ctx.lineTo(S, i * step); ctx.stroke();
    }
    for (let i = 0; i < g; i++) {
      ctx.fillText('ABCDEFGH'[i] || i, i * step + 4, 12);
      ctx.fillText(String(i + 1), 3, i * step + 24);
    }
    ctx.restore();
  }

  // calor: densidad en una rejilla, suavizada y coloreada con el color de la capa
  drawHeat(ctx, L) {
    const S = this.size, cell = 4, n = Math.ceil(S / cell);
    const grid = new Float32Array(n * n);
    for (const p of L.points) {
      const [x, y] = this.toPx(p[0], p[1]);
      const i = Math.floor(x / cell), j = Math.floor(y / cell);
      if (i >= 0 && j >= 0 && i < n && j < n) grid[j * n + i]++;
    }
    const rad = Math.max(1, Math.round((L.radius || 12) / cell));
    const blur = (src, horiz) => {
      const out = new Float32Array(n * n);
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
        let s = 0;
        for (let k = -rad; k <= rad; k++) {
          const ii = horiz ? i + k : i, jj = horiz ? j : j + k;
          if (ii >= 0 && jj >= 0 && ii < n && jj < n) s += src[jj * n + ii];
        }
        out[j * n + i] = s;
      }
      return out;
    };
    const d = blur(blur(grid, true), false);
    let max = 0; for (const v of d) if (v > max) max = v;
    if (!max) return;
    const off = document.createElement('canvas'); off.width = off.height = n;
    const octx = off.getContext('2d'), img = octx.createImageData(n, n);
    const c = parseInt((L.color || COLORS.neutral).slice(1), 16);
    for (let k = 0; k < n * n; k++) {
      const v = Math.sqrt(d[k] / max); // raíz: que se vean también las zonas poco visitadas
      img.data[k * 4] = (c >> 16) & 255; img.data[k * 4 + 1] = (c >> 8) & 255; img.data[k * 4 + 2] = c & 255;
      img.data[k * 4 + 3] = v < 0.04 ? 0 : Math.round(235 * v);
    }
    octx.putImageData(img, 0, 0);
    ctx.save(); ctx.imageSmoothingEnabled = true; ctx.drawImage(off, 0, 0, S, S); ctx.restore();
  }

  drawPoints(ctx, L) {
    ctx.save();
    ctx.fillStyle = L.color || COLORS.us;
    ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 1;
    const r = L.radius || 4;
    for (const p of L.points) {
      const [x, y] = this.toPx(p[0], p[1]);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    ctx.restore();
  }

  drawCrosses(ctx, L) {
    ctx.save();
    const r = L.radius || 5;
    for (const p of L.points) {
      const [x, y] = this.toPx(p[0], p[1]);
      ctx.strokeStyle = 'rgba(0,0,0,.7)'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r); ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke();
      ctx.strokeStyle = p[4] || L.color || COLORS.them; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r); ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke();
    }
    ctx.restore();
  }

  drawMarkers(ctx, L) {
    ctx.save();
    ctx.font = 'bold 12px system-ui';
    for (const m of L.points) {
      const [x, y] = this.toPx(m[0], m[1]);
      ctx.fillStyle = m[3] || ink();
      ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = ink(); ctx.fillText(m[2] || '', x + 8, y + 4);
    }
    ctx.restore();
  }

  /** Imágenes cargadas desde /img/... centradas en su posición; si no cargan (o no tienen src), un círculo —o rombo con shape 'diamond'— de color `color`/`label`. */
  drawImages(ctx, L) {
    this.imgCache = this.imgCache || new Map();
    ctx.save();
    for (const it of L.items) {
      const [x, y] = this.toPx(it.x, it.y);
      const s = it.size || 24;
      let img = null;
      if (it.src) {
        if (!this.imgCache.has(it.src)) {
          const im = new Image();
          const rec = { im, ok: false };
          im.onload = () => { rec.ok = true; this.draw(); };
          im.src = it.src;
          this.imgCache.set(it.src, rec);
        }
        const rec = this.imgCache.get(it.src);
        if (rec.ok) img = rec.im;
      }
      if (img) {
        const k = Math.min(s / img.naturalWidth, s / img.naturalHeight);
        const w = img.naturalWidth * k, h = img.naturalHeight * k;
        ctx.drawImage(img, x - w / 2, y - h / 2, w, h);
      } else {
        ctx.fillStyle = it.color || it.label || COLORS.neutral;
        ctx.strokeStyle = 'rgba(0,0,0,.8)'; ctx.lineWidth = 2;
        ctx.beginPath();
        if (it.shape === 'diamond') { const r = s / 2; ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); }
        else ctx.arc(x, y, s / 3, 0, Math.PI * 2);
        ctx.fill(); ctx.stroke();
      }
    }
    ctx.restore();
  }

  drawPaths(ctx, L) {
    ctx.save();
    ctx.strokeStyle = L.color || COLORS.us; ctx.globalAlpha = L.alpha || 0.6; ctx.lineWidth = L.width || 1.5;
    ctx.lineJoin = 'round';
    for (const path of L.paths) {
      ctx.beginPath(); let pen = false;
      for (const p of path) {
        if (!p) { pen = false; continue; }
        const [x, y] = this.toPx(p[0], p[1]);
        if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  // celdas en coordenadas de cuadrícula ya calculadas en el servidor: [col, fila, valor]
  drawCells(ctx, L) {
    const S = this.size, g = this.grid || 8, step = S / g;
    const maxAbs = Math.max(1, ...L.cells.map(c => Math.abs(c[2])));
    ctx.save();
    ctx.font = 'bold 12px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const [cx, cy, v] of L.cells) {
      let col = cx, row = cy;
      if (this.rotate) { col = g - 1 - cx; row = g - 1 - cy; }
      const a = 0.12 + 0.5 * Math.abs(v) / maxAbs;
      ctx.fillStyle = L.diverging ? (v >= 0 ? hexA(COLORS.us, a) : hexA(COLORS.them, a)) : hexA(L.color || COLORS.us, a);
      ctx.fillRect(col * step + 1, row * step + 1, step - 2, step - 2);
      if (L.labels) {
        ctx.fillStyle = ink();
        ctx.fillText((L.diverging && v > 0 ? '+' : '') + v, col * step + step / 2, row * step + step / 2);
      }
    }
    ctx.restore();
  }

  exportPNG(name = 'mapa.png') {
    this.canvas.toBlob(b => downloadBlob(name, b), 'image/png');
  }
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export function legend(items) {
  return el('div', { class: 'legend' }, items.map(([color, label, shape]) =>
    el('span', {}, el('i', { style: { background: shape === 'x' ? 'none' : color, border: shape === 'x' ? `2px solid ${color}` : null } }), label)));
}

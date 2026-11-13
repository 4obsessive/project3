// Gráficas SVG sencillas: barras, histograma, líneas y línea de tiempo.
import { el, fmt, cssVar } from './util.js';
import { objectiveSrc, laneStyle } from './art.js';

const NS = 'http://www.w3.org/2000/svg';
// Colores leídos de los tokens CSS (app.css :root): una sola fuente para gráficas, mapa y leyendas.
export const SIDE_COLORS = {
  get us() { return cssVar('--us', '#3fbf7f'); },
  get them() { return cssVar('--them', '#e5534b'); },
  get t0() { return cssVar('--t0', '#e0a030'); },
  get t1() { return cssVar('--t1', '#4d84ff'); },
  get neutral() { return cssVar('--neutral', '#9aa1ad'); },
};
const palette = i => cssVar(`--c${(i % 7) + 1}`, '#d6a548');
const gridColor = () => cssVar('--grid', '#2e333d');
let uid = 0;

function s(tag, attrs = {}, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  for (const k of kids) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
const colorOf = (ser, i) => ser.color || (ser.side ? SIDE_COLORS[ser.side] : null) || palette(i);
// «them» (y t1) se rayan para distinguir lados sin depender del color
const hatched = ser => ser.side === 'them' || ser.side === 't1';

function svgRoot(W, H, label, fixedWidth = true) {
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': label || 'Chart' });
  if (fixedWidth) svg.style.maxWidth = W + 'px';
  if (label) svg.append(s('title', {}, label));
  return svg;
}
function hatchPattern(svg, color) {
  const id = 'hatch' + (++uid);
  svg.append(s('defs', {}, s('pattern', { id, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
    s('rect', { width: 6, height: 6, fill: color }), s('rect', { width: 2.5, height: 6, fill: 'rgba(0,0,0,.45)' }))));
  return `url(#${id})`;
}


function legendFor(series) {
  if (series.length < 2) return null;
  return el('div', { class: 'legend' }, series.map((sr, i) => el('span', {}, el('i', { class: hatched(sr) ? 'hatch' : null, style: { background: colorOf(sr, i) } }), sr.name)));
}

/** Barras agrupadas verticales. labels: [...], series: [{name, values, side}] */
/** labelColor(label, index) -> color|null: pinta la etiqueta del eje X (y la subraya) con ese color (p. ej. carriles). */
export function bars({ labels, series, unit = '', height = 220, label = '', labelColor = null }) {
  const W = Math.max(320, labels.length * (series.length * 26 + 30) + 60), H = height, P = { l: 44, r: 10, t: 14, b: 46 };
  const vals = series.flatMap(sr => [...sr.values, ...(sr.ci || []).flat()]).filter(v => v != null);
  const max = Math.max(0, ...vals), min = Math.min(0, ...vals);
  const span = (max - min) || 1;
  const y = v => P.t + (H - P.t - P.b) * (1 - (v - min) / span);
  const svg = svgRoot(W, H, label || `Barras: ${series.map(sr => sr.name).join(' vs ')}`);
  svg.style.color = cssVar('--text', '#eee');
  const fills = series.map((sr, j) => hatched(sr) ? hatchPattern(svg, colorOf(sr, j)) : colorOf(sr, j));
  for (const tv of ticks(min, max)) {
    svg.append(s('line', { x1: P.l, x2: W - P.r, y1: y(tv), y2: y(tv), stroke: gridColor() }));
    svg.append(s('text', { x: P.l - 6, y: y(tv) + 4, 'text-anchor': 'end' }, short(tv) + unit));
  }
  const gw = (W - P.l - P.r) / labels.length, bw = Math.min(28, (gw - 12) / series.length);
  labels.forEach((lab, i) => {
    series.forEach((sr, j) => {
      const v = sr.values[i]; if (v == null) return;
      const x = P.l + i * gw + (gw - bw * series.length) / 2 + j * bw;
      const y0 = y(Math.max(0, v)), y1 = y(Math.min(0, v));
      svg.append(s('rect', { x, y: y0, width: bw - 2, height: Math.max(1, y1 - y0), fill: fills[j], rx: 2 }, s('title', {}, `${sr.name}: ${v}${unit}`)));
      // etiqueta de valor solo si la barra es lo bastante ancha para leerla
      const ci = sr.ci?.[i];
      if (ci) {  // bigote del intervalo de confianza
        const cx = x + bw / 2 - 1;
        svg.append(s('line', { class: 'whisker', x1: cx, x2: cx, y1: y(ci[1]), y2: y(ci[0]), stroke: 'currentColor', 'stroke-width': 1.5 }, s('title', {}, `IC90 ${ci[0]}–${ci[1]}${unit}`)));
        for (const e of ci) svg.append(s('line', { x1: cx - 4, x2: cx + 4, y1: y(e), y2: y(e), stroke: 'currentColor', 'stroke-width': 1.5 }));
      }
      if (bw >= 22 && !ci) svg.append(s('text', { class: 'val', x: x + bw / 2 - 1, y: v >= 0 ? y0 - 3 : y1 + 12, 'text-anchor': 'middle' }, short(v) + unit));
    });
    const lc = labelColor ? labelColor(lab, i) : null;
    const lx = P.l + i * gw + gw / 2, shown = trunc(lab, Math.floor(gw / 6.5));
    svg.append(s('text', lc ? { x: lx, y: H - P.b + 16, 'text-anchor': 'middle', fill: lc, 'font-weight': 600 } : { x: lx, y: H - P.b + 16, 'text-anchor': 'middle' }, shown));
    if (lc) { const hw = Math.min(gw - 8, shown.length * 6.5) / 2; svg.append(s('line', { x1: lx - hw, x2: lx + hw, y1: H - P.b + 21, y2: H - P.b + 21, stroke: lc, 'stroke-width': 3, 'stroke-linecap': 'round' })); }
  });
  return el('div', {}, legendFor(series), svg);
}

/** Histograma de valores en segundos agrupados en bins (bin_s). */
export function histogram({ series, bin_s = 60, height = 200, label = '' }) {
  const all = series.flatMap(sr => sr.values).filter(v => v != null);
  if (!all.length) return el('div', { class: 'muted small' }, 'No data');
  const lo = Math.floor(Math.min(...all) / bin_s), hi = Math.floor(Math.max(...all) / bin_s);
  const labels = [], counts = series.map(() => []);
  for (let b = lo; b <= hi; b++) {
    labels.push(bin_s % 60 === 0 ? `${b * bin_s / 60}′` : fmt.mmss(b * bin_s));
    series.forEach((sr, i) => counts[i].push(sr.values.filter(v => v != null && Math.floor(v / bin_s) === b).length));
  }
  return bars({ labels, series: series.map((sr, i) => ({ ...sr, values: counts[i] })), height, label: label || `Histogram: ${series.map(sr => sr.name).join(' vs ')}` });
}

/** Líneas temporales. series: [{name, points:[[t, v]], color}], invert para rangos (1 arriba). */
export function lines({ series, height = 160, invert = false, yfmt = v => short(v), xfmt = t => fmt.date(t), label = '' }) {
  const pts = series.flatMap(sr => [...sr.points, ...(sr.band || []).flatMap(b => [[b[0], b[1]], [b[0], b[2]]])]).filter(p => p[1] != null);
  if (!pts.length) return el('div', { class: 'muted small' }, 'No history yet');
  const W = 560, H = height, P = { l: 44, r: 10, t: 10, b: 24 };
  let x0 = Math.min(...pts.map(p => p[0])), x1 = Math.max(...pts.map(p => p[0]));
  let y0 = Math.min(...pts.map(p => p[1])), y1 = Math.max(...pts.map(p => p[1]));
  if (x0 === x1) { x0 -= 3600; x1 += 3600; }
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const X = t => P.l + (W - P.l - P.r) * (t - x0) / (x1 - x0);
  const Y = v => { const f = (v - y0) / (y1 - y0); return P.t + (H - P.t - P.b) * (invert ? f : 1 - f); };
  const svg = svgRoot(W, H, label || `Trend: ${series.map(sr => sr.name).join(', ')}`);
  for (const tv of ticks(y0, y1)) {
    svg.append(s('line', { x1: P.l, x2: W - P.r, y1: Y(tv), y2: Y(tv), stroke: gridColor() }));
    svg.append(s('text', { x: P.l - 6, y: Y(tv) + 4, 'text-anchor': 'end' }, yfmt(tv)));
  }
  // marcas intermedias del eje X (extremos + 3 intermedias, sin repetir etiquetas)
  const NX = 4; let prev = null;
  for (let i = 0; i <= NX; i++) {
    const t = x0 + (x1 - x0) * i / NX, lab = xfmt(t);
    if (lab === prev) continue; prev = lab;
    svg.append(s('line', { x1: X(t), x2: X(t), y1: H - P.b, y2: H - P.b + 4, stroke: gridColor() }));
    svg.append(s('text', { x: X(t), y: H - 6, 'text-anchor': i === 0 ? 'start' : i === NX ? 'end' : 'middle' }, lab));
  }
  series.forEach((sr, i) => {
    const p = sr.points.filter(p => p[1] != null);
    const c = colorOf(sr, i);
    if (sr.band?.length > 1) {
      const up = sr.band.map(b => `${X(b[0])},${Y(b[2])}`), dn = sr.band.slice().reverse().map(b => `${X(b[0])},${Y(b[1])}`);
      svg.append(s('polygon', { points: [...up, ...dn].join(' '), fill: c, 'fill-opacity': .14, stroke: 'none' }));
    }
    if (sr.ref != null) svg.append(s('line', { x1: P.l, x2: W - P.r, y1: Y(sr.ref), y2: Y(sr.ref), stroke: c, 'stroke-opacity': .4, 'stroke-dasharray': '3 4' }));
    svg.append(s('polyline', { points: p.map(q => `${X(q[0])},${Y(q[1])}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 2 }));
    for (const q of p) svg.append(s('circle', { cx: X(q[0]), cy: Y(q[1]), r: 3, fill: c }, s('title', {}, `${xfmt(q[0])}: ${yfmt(q[1])}`)));
  });
  return el('div', {}, legendFor(series), svg);
}

/** Línea de tiempo: rows [{label, duration, events:[{t, label, side, kind}]}].
 *  Eventos con objetivo conocido llevan su imagen (≤ 22 px) con borde del color del lado (contorno discontinuo = «them»/t1).
 *  lanes: {id:{nombre,color}}; una fila cuyo label empieza por un nombre de carril lleva una franja de su color. */
export function timeline({ rows, lanes = null, label = '' }) {
  const maxT = Math.max(60, ...rows.map(r => r.duration || 0), ...rows.flatMap(r => r.events.map(e => e.t || 0)));
  const W = 900, rowH = 26, P = { l: 120, r: 10, t: 20 };
  const H = P.t + rows.length * rowH + 10;
  const X = t => P.l + (W - P.l - P.r) * t / maxT;
  const svg = svgRoot(W, H, label || `Timeline: ${rows.map(r => r.label).join(', ')}`, false);
  svg.classList.add('timeline');
  for (let m = 0; m <= maxT / 60; m++) {
    const major = m % 5 === 0;
    svg.append(s('line', { x1: X(m * 60), x2: X(m * 60), y1: major ? P.t - 4 : P.t, y2: H, stroke: gridColor(), 'stroke-opacity': major ? 1 : 0.35 }));
    if (major) svg.append(s('text', { x: X(m * 60), y: 12, 'text-anchor': 'middle' }, `${m}′`));
  }
  const shape = { Guardian: 'diamond', Walker: 'rect', 'Base guardian': 'diamond', Shrine: 'tri', Titan: 'star', Core: 'star' };
  const laneIds = Object.keys(lanes || {});
  const laneOfRow = r => { const l = String(r.label || '').toLowerCase(); const id = laneIds.find(i => lanes[i].nombre && l.startsWith(String(lanes[i].nombre).toLowerCase())); return id ? laneStyle(id, lanes) : null; };
  // marcador de forma (sin imagen): también es el recurso cuando la imagen no carga
  const shapeNode = (kind, x, cy) => {
    if (kind === 'rect') return s('rect', { x: x - 4, y: cy - 4, width: 8, height: 8 });
    if (kind === 'diamond') return s('polygon', { points: `${x},${cy - 7} ${x + 6},${cy} ${x},${cy + 7} ${x - 6},${cy}` });
    if (kind === 'tri') return s('polygon', { points: `${x},${cy - 6} ${x + 5},${cy + 4} ${x - 5},${cy + 4}` });
    if (kind === 'star') return s('polygon', { points: `${x},${cy - 7} ${x + 2},${cy - 2} ${x + 7},${cy - 2} ${x + 3},${cy + 2} ${x + 4},${cy + 7} ${x},${cy + 4} ${x - 4},${cy + 7} ${x - 3},${cy + 2} ${x - 7},${cy - 2} ${x - 2},${cy - 2}` });
    return s('circle', { cx: x, cy, r: 4 });
  };
  let hasImg = false;
  rows.forEach((r, i) => {
    const cy = P.t + i * rowH + rowH / 2;
    const lane = laneOfRow(r);
    if (lane) svg.append(s('rect', { x: 0, y: cy - rowH / 2 + 2, width: 4, height: rowH - 4, rx: 2, fill: lane.color }, s('title', {}, lane.nombre)));
    svg.append(s('text', { x: P.l - 8, y: cy + 4, 'text-anchor': 'end' }, trunc(r.label, 18)));
    svg.append(s('line', { x1: X(0), x2: X(r.duration || maxT), y1: cy, y2: cy, stroke: lane ? lane.color : cssVar('--track', '#3a404b'), 'stroke-opacity': lane ? 0.6 : 1 }));
    for (const e of r.events) {
      const x = X(e.t), c = (e.side && SIDE_COLORS[e.side]) || e.color || SIDE_COLORS.neutral;
      const kind = shape[e.kind] || 'circle';
      // «them»/t1 huecos (solo contorno): distinguibles sin color
      const paint = hatched(e) ? { fill: 'none', stroke: c, 'stroke-width': 2 } : { fill: c };
      const g = s('g', {}, s('title', {}, `${fmt.mmss(e.t)} · ${e.label}`));
      const src = e.kind ? objectiveSrc(e.kind, e.owner) : null;
      const plain = () => { const node = shapeNode(kind, x, cy); for (const [k, v] of Object.entries(paint)) node.setAttribute(k, v); return node; };
      if (src) {
        hasImg = true;
        const frame = s('rect', { x: x - 11, y: cy - 11, width: 22, height: 22, rx: 4, fill: 'rgba(0,0,0,.35)', stroke: c, 'stroke-width': 2, 'stroke-dasharray': hatched(e) ? '4 2' : null });
        const img = s('image', { href: src, x: x - 9, y: cy - 9, width: 18, height: 18, preserveAspectRatio: 'xMidYMid meet' });
        img.addEventListener('error', () => { frame.remove(); img.replaceWith(plain()); });
        g.append(frame, img);
      } else g.append(plain());
      svg.append(g);
    }
  });
  const leg = el('div', { class: 'legend' },
    el('span', {}, hasImg ? 'Each event shows its objective image (◆ Guardian)' : '◆ Guardian · ■ Walker · ▲ Shrine · ★ Titan/Core'),
    ...(rows.some(r => r.events.some(e => e.side === 'us')) ? [el('span', {}, el('i', { style: { background: SIDE_COLORS.us } }), 'this team destroys (solid border)'), el('span', { style: { color: SIDE_COLORS.them } }, el('i', { class: 'hollow' }), el('span', { class: 'muted' }, 'loses (dashed border)'))] : []),
    ...(rows.some(r => r.events.some(e => e.side === 't0' || e.side === 't1')) ? [el('span', {}, el('i', { style: { background: SIDE_COLORS.t0 } }), 'team 0 (filled)'), el('span', { style: { color: SIDE_COLORS.t1 } }, el('i', { class: 'hollow' }), el('span', { class: 'muted' }, 'team 1 (outline)'))] : []));
  return el('div', {}, leg, el('div', { class: 'chart-scroll' }, svg));
}

function ticks(min, max, n = 4) {
  const span = max - min || 1;
  const step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = span / n / step;
  const st = step * (err >= 5 ? 10 : err >= 2 ? 5 : err >= 1.5 ? 2 : 1);
  const out = [];
  for (let v = Math.ceil(min / st) * st; v <= max + 1e-9; v += st) out.push(+v.toFixed(6));
  return out;
}
function short(v) {
  if (v == null) return '';
  const a = Math.abs(v);
  if (a >= 10000) return (v / 1000).toFixed(0) + 'k';
  if (a >= 1000) return (v / 1000).toFixed(1) + 'k';
  return Number.isInteger(v) ? String(v) : v.toFixed(a < 10 ? 2 : 1);
}
function trunc(t, n) { t = String(t); return t.length > n ? t.slice(0, Math.max(1, n - 1)) + '…' : t; }

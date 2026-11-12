// Gráficas SVG sencillas: barras, histograma, líneas y línea de tiempo.
import { el, fmt } from './util.js';

const NS = 'http://www.w3.org/2000/svg';
export const SIDE_COLORS = { us: '#3fbf7f', them: '#e5534b', t0: '#e0a030', t1: '#4d84ff' };
const PALETTE = ['#d6a548', '#4d84ff', '#3fbf7f', '#e5534b', '#9b7be0', '#45c1c9', '#e07bb5'];

function s(tag, attrs = {}, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  for (const k of kids) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
const colorOf = (ser, i) => ser.color || SIDE_COLORS[ser.side] || PALETTE[i % PALETTE.length];

function legendFor(series) {
  if (series.length < 2) return null;
  return el('div', { class: 'legend' }, series.map((sr, i) => el('span', {}, el('i', { style: { background: colorOf(sr, i) } }), sr.name)));
}

/** Barras agrupadas verticales. labels: [...], series: [{name, values, side}] */
export function bars({ labels, series, unit = '', height = 220 }) {
  const W = Math.max(320, labels.length * (series.length * 26 + 30) + 60), H = height, P = { l: 44, r: 10, t: 14, b: 46 };
  const vals = series.flatMap(sr => sr.values).filter(v => v != null);
  const max = Math.max(0, ...vals), min = Math.min(0, ...vals);
  const span = (max - min) || 1;
  const y = v => P.t + (H - P.t - P.b) * (1 - (v - min) / span);
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', style: `max-width:${W}px` });
  for (const tv of ticks(min, max)) {
    svg.append(s('line', { x1: P.l, x2: W - P.r, y1: y(tv), y2: y(tv), stroke: '#2e333d' }));
    svg.append(s('text', { x: P.l - 6, y: y(tv) + 4, 'text-anchor': 'end' }, short(tv) + unit));
  }
  const gw = (W - P.l - P.r) / labels.length, bw = Math.min(28, (gw - 12) / series.length);
  labels.forEach((lab, i) => {
    series.forEach((sr, j) => {
      const v = sr.values[i]; if (v == null) return;
      const x = P.l + i * gw + (gw - bw * series.length) / 2 + j * bw;
      const y0 = y(Math.max(0, v)), y1 = y(Math.min(0, v));
      svg.append(s('rect', { x, y: y0, width: bw - 2, height: Math.max(1, y1 - y0), fill: colorOf(sr, j), rx: 2 }, s('title', {}, `${sr.name}: ${v}${unit}`)));
      svg.append(s('text', { x: x + bw / 2 - 1, y: v >= 0 ? y0 - 3 : y1 + 11, 'text-anchor': 'middle' }, short(v) + unit));
    });
    svg.append(s('text', { x: P.l + i * gw + gw / 2, y: H - P.b + 16, 'text-anchor': 'middle' }, trunc(lab, Math.floor(gw / 6.5))));
  });
  return el('div', {}, legendFor(series), svg);
}

/** Histograma de valores en segundos agrupados en bins (bin_s). */
export function histogram({ series, bin_s = 60, height = 200 }) {
  const all = series.flatMap(sr => sr.values).filter(v => v != null);
  if (!all.length) return el('div', { class: 'muted small' }, 'Sin datos');
  const lo = Math.floor(Math.min(...all) / bin_s), hi = Math.floor(Math.max(...all) / bin_s);
  const labels = [], counts = series.map(() => []);
  for (let b = lo; b <= hi; b++) {
    labels.push(bin_s % 60 === 0 ? `${b * bin_s / 60}′` : fmt.mmss(b * bin_s));
    series.forEach((sr, i) => counts[i].push(sr.values.filter(v => v != null && Math.floor(v / bin_s) === b).length));
  }
  return bars({ labels, series: series.map((sr, i) => ({ ...sr, values: counts[i] })), height });
}

/** Líneas temporales. series: [{name, points:[[t, v]], color}], invert para rangos (1 arriba). */
export function lines({ series, height = 160, invert = false, yfmt = v => short(v), xfmt = t => fmt.date(t) }) {
  const pts = series.flatMap(sr => sr.points).filter(p => p[1] != null);
  if (!pts.length) return el('div', { class: 'muted small' }, 'Sin historial todavía');
  const W = 560, H = height, P = { l: 44, r: 10, t: 10, b: 24 };
  let x0 = Math.min(...pts.map(p => p[0])), x1 = Math.max(...pts.map(p => p[0]));
  let y0 = Math.min(...pts.map(p => p[1])), y1 = Math.max(...pts.map(p => p[1]));
  if (x0 === x1) { x0 -= 3600; x1 += 3600; }
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const X = t => P.l + (W - P.l - P.r) * (t - x0) / (x1 - x0);
  const Y = v => { const f = (v - y0) / (y1 - y0); return P.t + (H - P.t - P.b) * (invert ? f : 1 - f); };
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', style: `max-width:${W}px` });
  for (const tv of ticks(y0, y1)) {
    svg.append(s('line', { x1: P.l, x2: W - P.r, y1: Y(tv), y2: Y(tv), stroke: '#2e333d' }));
    svg.append(s('text', { x: P.l - 6, y: Y(tv) + 4, 'text-anchor': 'end' }, yfmt(tv)));
  }
  svg.append(s('text', { x: P.l, y: H - 6 }, xfmt(x0)));
  svg.append(s('text', { x: W - P.r, y: H - 6, 'text-anchor': 'end' }, xfmt(x1)));
  series.forEach((sr, i) => {
    const p = sr.points.filter(p => p[1] != null);
    const c = colorOf(sr, i);
    svg.append(s('polyline', { points: p.map(q => `${X(q[0])},${Y(q[1])}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 2 }));
    for (const q of p) svg.append(s('circle', { cx: X(q[0]), cy: Y(q[1]), r: 3, fill: c }, s('title', {}, `${xfmt(q[0])}: ${yfmt(q[1])}`)));
  });
  return el('div', {}, legendFor(series), svg);
}

/** Línea de tiempo: rows [{label, duration, events:[{t, label, side, kind}]}] */
export function timeline({ rows }) {
  const maxT = Math.max(60, ...rows.map(r => r.duration || 0), ...rows.flatMap(r => r.events.map(e => e.t || 0)));
  const W = 900, rowH = 22, P = { l: 120, r: 10, t: 20 };
  const H = P.t + rows.length * rowH + 10;
  const X = t => P.l + (W - P.l - P.r) * t / maxT;
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%' });
  for (let m = 0; m <= maxT / 60; m += 5) {
    svg.append(s('line', { x1: X(m * 60), x2: X(m * 60), y1: P.t - 4, y2: H, stroke: '#2e333d' }));
    svg.append(s('text', { x: X(m * 60), y: 12, 'text-anchor': 'middle' }, `${m}′`));
  }
  const shape = { Guardian: 'circle', Walker: 'rect', 'Base guardian': 'diamond', Shrine: 'tri', Titan: 'star', Core: 'star' };
  rows.forEach((r, i) => {
    const cy = P.t + i * rowH + rowH / 2;
    svg.append(s('text', { x: P.l - 8, y: cy + 4, 'text-anchor': 'end' }, trunc(r.label, 18)));
    svg.append(s('line', { x1: X(0), x2: X(r.duration || maxT), y1: cy, y2: cy, stroke: '#3a404b' }));
    for (const e of r.events) {
      const x = X(e.t), c = SIDE_COLORS[e.side] || e.color || '#999';
      const kind = shape[e.kind] || 'circle';
      let node;
      if (kind === 'rect') node = s('rect', { x: x - 4, y: cy - 4, width: 8, height: 8, fill: c });
      else if (kind === 'diamond') node = s('polygon', { points: `${x},${cy - 6} ${x + 5},${cy} ${x},${cy + 6} ${x - 5},${cy}`, fill: c });
      else if (kind === 'tri') node = s('polygon', { points: `${x},${cy - 6} ${x + 5},${cy + 4} ${x - 5},${cy + 4}`, fill: c });
      else if (kind === 'star') node = s('polygon', { points: `${x},${cy - 7} ${x + 2},${cy - 2} ${x + 7},${cy - 2} ${x + 3},${cy + 2} ${x + 4},${cy + 7} ${x},${cy + 4} ${x - 4},${cy + 7} ${x - 3},${cy + 2} ${x - 7},${cy - 2} ${x - 2},${cy - 2}`, fill: c });
      else node = s('circle', { cx: x, cy, r: 4, fill: c });
      node.append(s('title', {}, `${fmt.mmss(e.t)} · ${e.label}`));
      svg.append(node);
    }
  });
  const leg = el('div', { class: 'legend' },
    el('span', {}, '● Guardian · ■ Walker · ◆ Base guardian · ▲ Shrine · ★ Titan/Core'),
    ...(rows.some(r => r.events.some(e => e.side === 'us')) ? [el('span', {}, el('i', { style: { background: SIDE_COLORS.us } }), 'este equipo destruye'), el('span', {}, el('i', { style: { background: SIDE_COLORS.them } }), 'pierde')] : []));
  return el('div', {}, leg, el('div', { class: 'tablewrap' }, svg));
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

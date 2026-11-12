// Render genérico de bloques del informe. La web NO conoce las métricas: solo los tipos de bloque.
import { el, dataTable } from './util.js';
import { bars, histogram, timeline, SIDE_COLORS } from './charts.js';
import { MapView, legend } from './map.js';
import { laneChip, laneStyle, objectiveImg } from './art.js';

// Carriles del informe ({id:{nombre,color,alias}}): los fija la vista del informe antes de pintar las secciones.
let LANES = null;
export function setLanes(l) { LANES = l; }
const SECTION_ART = { midboss: 'Midboss', koth: 'KOTH' };  // secciones con imagen de objetivo en el título
const laneName = id => laneStyle(id, LANES).nombre;

// «Guardian York → Walker Greenwich» (texto plano) y su versión con imágenes y color de carril
export function laneSeqText(seq) { return (seq || []).map(s => `${s.tipo} ${laneName(s.carril)}`).join(' → '); }
function laneSeqCell(seq) {
  const wrap = el('span', { class: 'lane-seq', style: { display: 'inline-flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }, 'aria-label': laneSeqText(seq) });
  (seq || []).forEach((s, i) => {
    const ls = laneStyle(s.carril, LANES);
    if (i) wrap.append(el('span', { 'aria-hidden': 'true', class: 'muted' }, '→'));
    const img = objectiveImg(s.tipo, null, { size: 'sm' });
    wrap.append(el('span', { title: `${s.tipo} · ${ls.nombre}`, style: { display: 'inline-flex', flexDirection: 'column', alignItems: 'center' } },
      img, el('span', { 'aria-hidden': 'true', style: { display: 'block', width: '100%', minWidth: '14px', height: '3px', borderRadius: '2px', background: ls.color } })));
  });
  return wrap;
}
const laneCol = c => c.fmt === 'evidence' ? { render: r => r[c.key] ? el('span', { class: 'ev-chip ' + r[c.key] }, r[c.key]) : '' }
  : c.fmt === 'lane' ? { render: r => laneChip(r.carril_id, LANES) }
  : c.fmt === 'lane_seq' ? { render: r => laneSeqCell(r[c.key]), sort: r => laneSeqText(r[c.key]), sortable: false } : {};

const TONE = { confirmed: 'confirmado', interpretation: 'interpretación', warning: 'aviso', info: 'nota' };

export function renderBlock(b) {
  const title = (t, n) => t ? el('div', { class: 'chart-title' }, el('b', {}, t), n != null ? el('span', { class: 'n-badge' }, `n = ${n} partidas`) : null) : null;
  switch (b.type) {
    case 'text':
      return el('div', { class: `note ${b.tone || 'info'} block` }, el('span', { class: 'lbl' }, TONE[b.tone] || ''), b.text);
    case 'unavailable':
      return el('div', { class: 'unavailable block' }, el('b', {}, `No disponible — ${b.title}: `), b.reason);
    case 'table':
      return el('div', { class: 'block' }, title(b.title, b.n), b.note ? el('div', { class: 'muted small' }, b.note) : null,
        dataTable(b.columns.map(c => ({ key: c.key, label: c.label, fmt: c.fmt, wrap: c.key === 'texto', ...laneCol(c) })), b.rows, { label: b.title, emptyText: 'Sin datos' }));
    case 'bars':
      return el('div', { class: 'block' }, title(b.title, b.n), bars({ labels: b.labels, series: b.series, unit: b.unit || '', label: b.title,
        labelColor: b.lane_ids ? (lab, i) => laneStyle(b.lane_ids[i], LANES).color : null }));
    case 'histogram':
      return el('div', { class: 'block' }, title(b.title, b.n), histogram({ series: b.series, bin_s: b.bin_s || 60, label: b.title }));
    case 'timeline':
      return el('div', { class: 'block' }, title(b.title, b.n), timeline({ rows: b.rows, lanes: LANES, label: b.title }));
    case 'map': {
      const box = el('div');
      const wrap = el('div', { class: 'block' }, title(b.title, b.n));
      const leg = [];
      const layers = b.layers.map(L => {
        const color = (L.side && SIDE_COLORS[L.side]) || SIDE_COLORS.neutral;
        if (L.kind !== 'cells') leg.push([color, L.name, L.kind === 'crosses' ? 'x' : null]);
        else leg.push([SIDE_COLORS.us, 'balance positivo'], [SIDE_COLORS.them, 'balance negativo']);
        return { ...L, color, radius: L.kind === 'points' ? 4 : 5 };
      });
      wrap.append(legend(leg), box);
      if (b.normalized) wrap.append(el('div', { class: 'muted small' }, 'Normalizado: base propia siempre abajo.'));
      const map = new MapView(box, { size: 640, grid: b.grid || 0, label: b.title ? `Mapa: ${b.title}` : 'Mapa' });
      map.setLayers(layers);
      wrap.append(el('button', { class: 'no-print', onclick: () => map.exportPNG((b.title || 'mapa').replace(/\W+/g, '_') + '.png') }, 'Exportar PNG'));
      return wrap;
    }
    default:
      return el('div', { class: 'muted small' }, `Bloque desconocido: ${b.type}`);
  }
}

// el texto del título ya dice qué es: la imagen no se anuncia
function decorative(node) { node.setAttribute('aria-hidden', 'true'); if (node.tagName === 'IMG') node.alt = ''; node.removeAttribute('aria-label'); node.removeAttribute('role'); return node; }

export function renderSection(s) {
  const sec = el('div', { class: 'panel', id: 'sec-' + s.id }, el('h2', {}, SECTION_ART[s.id] ? decorative(objectiveImg(SECTION_ART[s.id], null, { size: 'md' })) : null, SECTION_ART[s.id] ? ' ' : null, s.title));
  if (s.error) sec.append(el('div', { class: 'section-error' }, `Esta sección falló: ${s.error}. El resto del informe es válido.`));
  for (const b of s.blocks) {
    try { sec.append(renderBlock(b)); } catch (e) { sec.append(el('div', { class: 'section-error' }, `No se pudo pintar un bloque: ${e.message}`)); }
  }
  return sec;
}

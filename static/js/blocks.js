// Render genérico de bloques del informe. La web NO conoce las métricas: solo los tipos de bloque.
import { el, dataTable, formatValue } from './util.js';
import { bars, histogram, timeline, SIDE_COLORS } from './charts.js';
import { MapView, legend } from './map.js';
import { heroPortrait, laneChip, laneStyle, objectiveImg } from './art.js';

// Carriles del informe ({id:{nombre,color,alias}}): los fija la vista del informe antes de pintar las secciones.
let LANES = null;
export function setLanes(l) { LANES = l; }
// Catálogo de héroes (id -> {name, wiki_image, image}) para los retratos; sin catálogo se usa «#id» y la inicial.
let HEROES = new Map();
export function setHeroes(list) { HEROES = new Map((list || []).map(h => [h.id, h])); }
const heroOf = id => HEROES.get(id) || { id, name: `#${id}` };

const SECTION_ART = { midboss: 'Midboss', koth: 'KOTH' };  // secciones con imagen de objetivo en el título
const laneName = id => laneStyle(id, LANES).nombre;

// el texto de al lado ya dice qué es: la imagen no se anuncia
function decorative(node) { node.setAttribute('aria-hidden', 'true'); if (node.tagName === 'IMG') node.alt = ''; node.removeAttribute('aria-label'); node.removeAttribute('role'); return node; }

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

/** Retratos pequeños de una lista de hero_id (hover = nombre). */
function heroStack(ids, size = 'sm') {
  const list = (ids || []).filter(id => id != null);
  if (!list.length) return null;
  return el('span', { class: 'hero-stack', title: list.map(id => heroOf(id).name).join(' + ') },
    list.map(id => heroPortrait(heroOf(id), { size, shape: 'round' })));
}

// celda «heroes»: retratos de r[ids] + el texto original (con sus conteos), que no se quita
function heroesCell(r, c) {
  const txt = r[c.key];
  const stack = heroStack(r[c.ids || 'hero_ids']);
  if (!stack) return txt == null || txt === '' ? '–' : String(txt);
  return el('span', { class: 'heroes-cell' }, stack, txt == null || txt === '' ? null : el('span', { class: 'heroes-txt' }, String(txt)));
}

// mini barra en la celda: valor / máximo (en valor absoluto) de la columna; el número sigue al lado
function barCell(r, c, max) {
  const v = r[c.key];
  const txt = formatValue(v, c.fmt);
  if (typeof v !== 'number' || !isFinite(v) || !max) return txt;
  const pct = Math.max(0, Math.min(100, 100 * Math.abs(v) / max));
  return el('span', { class: 'cell-bar' + (v < 0 ? ' neg' : '') },
    el('span', { class: 'cell-bar-track', 'aria-hidden': 'true' }, el('span', { class: 'cell-bar-fill', style: { width: pct + '%' } })),
    el('span', { class: 'cell-bar-val' }, txt));
}

function objectiveCell(r, c) {
  const txt = formatValue(r[c.key], null);
  return r.objective ? el('span', { class: 'obj-cell' }, decorative(objectiveImg(r.objective, null, { size: 'sm' })), txt) : txt;
}

// cabecera con la imagen del objetivo de la columna (el texto de la cabecera ya lo nombra)
function colLabel(c) {
  if (!c.objective) return c.label;
  return el('span', { class: 'th-obj' }, decorative(objectiveImg(c.objective, null, { size: 'sm' })), c.label);
}

function column(c, rows) {
  const base = { key: c.key, label: colLabel(c), fmt: c.fmt, wrap: c.key === 'texto' };
  if (c.fmt === 'evidence') return { ...base, render: r => r[c.key] ? el('span', { class: 'ev-chip ' + r[c.key] }, r[c.key]) : '' };
  if (c.fmt === 'lane') return { ...base, render: r => laneChip(r.carril_id, LANES) };
  if (c.fmt === 'lane_seq') return { ...base, render: r => laneSeqCell(r[c.key]), sort: r => laneSeqText(r[c.key]), sortable: false };
  if (c.fmt === 'heroes') return { ...base, render: r => heroesCell(r, c) };
  if (c.fmt === 'objective') return { ...base, render: r => objectiveCell(r, c) };
  if (c.bar) {
    const max = Math.max(0, ...rows.map(r => r[c.key]).filter(v => typeof v === 'number' && isFinite(v)).map(Math.abs));
    return { ...base, render: r => barCell(r, c, max) };
  }
  return base;
}

// Mapa al lado de una tabla (zonas resaltadas). Si no se puede crear, la tabla sigue sola.
function zoneMap(b) {
  try {
    const box = el('div', { class: 'table-map-map' });
    const layers = b.map.layers.map(L => ({ ...L, color: (L.side && SIDE_COLORS[L.side]) || SIDE_COLORS.neutral }));
    const leg = [];
    for (const L of layers) {
      const sides = new Set(L.cells.map(c => c[3] || L.side));
      if (sides.size <= 1) leg.push([L.color, L.name || 'Table zones']);
      else {
        if (sides.has('us')) leg.push([SIDE_COLORS.us, 'positive balance']);
        if (sides.has('them')) leg.push([SIDE_COLORS.them, 'negative balance']);
        if (sides.has('neutral')) leg.push([SIDE_COLORS.neutral, 'balance 0']);
      }
    }
    box.append(legend(leg));
    const map = new MapView(box, { size: 480, grid: b.map.grid || 0, label: `Map: ${b.title}` });
    map.setLayers(layers);
    if (b.map.normalized) box.append(el('div', { class: 'muted small' }, 'Normalized: own base always at the bottom.'));
    return box;
  } catch (e) { return null; }
}

// Tarjeta de dato destacado: retratos / objetivo / carril + valor + n
function card(it) {
  const visual = heroStack(it.hero_ids, 'md') || (it.objective ? decorative(objectiveImg(it.objective, null, { size: 'md' })) : null);
  const value = typeof it.value === 'number' ? formatValue(it.value, it.fmt || null) : (it.value ?? '–');
  return el('div', { class: 'stat-card' },
    visual ? el('div', { class: 'stat-card-visual' }, visual) : null,
    el('div', { class: 'stat-card-body' },
      el('div', { class: 'stat-card-title' }, it.title),
      el('div', { class: 'stat-card-value' }, el('b', {}, value), it.unit ? el('span', { class: 'stat-card-unit' }, ' ' + it.unit) : null),
      it.sub ? el('div', { class: 'stat-card-sub' }, it.sub) : null,
      el('div', { class: 'stat-card-foot' }, it.lane != null ? laneChip(it.lane, LANES) : null,
        it.n != null ? el('span', { class: 'n-badge' }, `n = ${it.n} ${it.n === 1 ? 'match' : 'matches'}`) : null)));
}

const TONE = { confirmed: 'confirmed', warning: 'warning', info: 'note' };

export function renderBlock(b) {
  const title = (t, n) => t ? el('div', { class: 'chart-title' }, el('b', {}, t), n != null ? el('span', { class: 'n-badge' }, `n = ${n} ${n === 1 ? 'match' : 'matches'}`) : null) : null;
  switch (b.type) {
    case 'text':
      return el('div', { class: `note ${b.tone || 'info'} block` }, el('span', { class: 'lbl' }, TONE[b.tone] || ''), b.text);
    case 'unavailable':
      return el('div', { class: 'unavailable block' }, el('b', {}, `Not available — ${b.title}: `), b.reason);
    case 'cards':
      return el('div', { class: 'stat-cards block', role: 'group', 'aria-label': b.title || 'Highlights' },
        b.title ? el('div', { class: 'chart-title' }, el('b', {}, b.title)) : null, (b.items || []).map(card));
    case 'table': {
      const tbl = dataTable(b.columns.map(c => column(c, b.rows)), b.rows, { label: b.title, emptyText: 'No data' });
      const head = [title(b.title, b.n), b.note ? el('div', { class: 'muted small' }, b.note) : null];
      const side = b.map && b.rows.length ? zoneMap(b) : null;
      if (!side) return el('div', { class: 'block' }, head, tbl);
      return el('div', { class: 'block' }, head, el('div', { class: 'table-map' }, el('div', { class: 'table-map-tbl' }, tbl), side));
    }
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
        else leg.push([SIDE_COLORS.us, 'positive balance'], [SIDE_COLORS.them, 'negative balance']);
        return { ...L, color, radius: L.kind === 'points' ? 4 : 5 };
      });
      wrap.append(legend(leg), box);
      if (b.normalized) wrap.append(el('div', { class: 'muted small' }, 'Normalized: own base always at the bottom.'));
      const map = new MapView(box, { size: 640, grid: b.grid || 0, label: b.title ? `Map: ${b.title}` : 'Map' });
      map.setLayers(layers);
      wrap.append(el('button', { class: 'no-print', onclick: () => map.exportPNG((b.title || 'map').replace(/\W+/g, '_') + '.png') }, 'Export PNG'));
      return wrap;
    }
    default:
      return el('div', { class: 'muted small' }, `Unknown block: ${b.type}`);
  }
}

export function renderSection(s) {
  const sec = el('div', { class: 'panel', id: 'sec-' + s.id }, el('h2', {}, SECTION_ART[s.id] ? decorative(objectiveImg(SECTION_ART[s.id], null, { size: 'md' })) : null, SECTION_ART[s.id] ? ' ' : null, s.title));
  if (s.error) sec.append(el('div', { class: 'section-error' }, `This section failed: ${s.error}. The rest of the report is valid.`));
  for (const b of s.blocks) {
    try { sec.append(renderBlock(b)); } catch (e) { sec.append(el('div', { class: 'section-error' }, `A block could not be drawn: ${e.message}`)); }
  }
  return sec;
}

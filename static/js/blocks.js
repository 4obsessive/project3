// Render genérico de bloques del informe. La web NO conoce las métricas: solo los tipos de bloque.
import { el, dataTable } from './util.js';
import { bars, histogram, timeline, SIDE_COLORS } from './charts.js';
import { MapView, legend } from './map.js';

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
        b.rows.length ? dataTable(b.columns.map(c => ({ key: c.key, label: c.label, fmt: c.fmt, wrap: c.key === 'texto' })), b.rows) : el('div', { class: 'muted small' }, 'Sin datos'));
    case 'bars':
      return el('div', { class: 'block' }, title(b.title, b.n), bars({ labels: b.labels, series: b.series, unit: b.unit || '' }));
    case 'histogram':
      return el('div', { class: 'block' }, title(b.title, b.n), histogram({ series: b.series, bin_s: b.bin_s || 60 }));
    case 'timeline':
      return el('div', { class: 'block' }, title(b.title, b.n), timeline({ rows: b.rows }));
    case 'map': {
      const box = el('div');
      const wrap = el('div', { class: 'block' }, title(b.title, b.n));
      const leg = [];
      const layers = b.layers.map(L => {
        const color = SIDE_COLORS[L.side] || '#555';
        if (L.kind !== 'cells') leg.push([color, L.name, L.kind === 'crosses' ? 'x' : null]);
        else leg.push([SIDE_COLORS.us, 'balance positivo'], [SIDE_COLORS.them, 'balance negativo']);
        return { ...L, color, radius: L.kind === 'points' ? 4 : 5 };
      });
      wrap.append(legend(leg), box);
      if (b.normalized) wrap.append(el('div', { class: 'muted small' }, 'Normalizado: base propia siempre abajo.'));
      const map = new MapView(box, { size: 640, grid: b.grid || 0 });
      map.setLayers(layers);
      wrap.append(el('button', { class: 'no-print', onclick: () => map.exportPNG((b.title || 'mapa').replace(/\W+/g, '_') + '.png') }, 'Exportar PNG'));
      return wrap;
    }
    default:
      return el('div', { class: 'muted small' }, `Bloque desconocido: ${b.type}`);
  }
}

export function renderSection(s) {
  const sec = el('div', { class: 'panel', id: 'sec-' + s.id }, el('h2', {}, s.title));
  if (s.error) sec.append(el('div', { class: 'section-error' }, `Esta sección falló: ${s.error}. El resto del informe es válido.`));
  for (const b of s.blocks) {
    try { sec.append(renderBlock(b)); } catch (e) { sec.append(el('div', { class: 'section-error' }, `No se pudo pintar un bloque: ${e.message}`)); }
  }
  return sec;
}

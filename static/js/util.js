// Utilidades comunes: DOM, formato, tablas ordenables, CSV, avisos.

export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith('--')) e.style.setProperty(sk, sv);
        else e.style[sk] = sv;
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}

export const fmt = {
  int: v => v == null ? '–' : Math.round(v).toLocaleString('es-ES'),
  dec: (v, d = 2) => v == null || !isFinite(v) ? '–' : Number(v).toFixed(d),
  pct: v => v == null || !isFinite(v) ? '–' : Math.round(v * 100) + '%',
  mmss: s => {
    if (s == null || !isFinite(s)) return '–';
    s = Math.round(s); const m = Math.floor(s / 60), r = s % 60;
    return `${m}:${String(r).padStart(2, '0')}`;
  },
  signed: (v, d = 1) => v == null || !isFinite(v) ? '–' : (v > 0 ? '+' : '') + Number(v).toFixed(d),
  signed0: v => v == null || !isFinite(v) ? '–' : (v > 0 ? '+' : '') + Math.round(v).toLocaleString('es-ES'),
  date: t => t ? new Date(t * 1000).toLocaleDateString('es-ES') : '–',
  datetime: t => t ? new Date(t * 1000).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '–',
  ago: t => {
    if (!t) return 'nunca';
    const s = Date.now() / 1000 - t;
    if (s < 90) return 'hace un momento';
    if (s < 3600) return `hace ${Math.round(s / 60)} min`;
    if (s < 86400 * 2) return `hace ${Math.round(s / 3600)} h`;
    return `hace ${Math.round(s / 86400)} días`;
  },
};

export function formatValue(v, f) {
  if (v === null || v === undefined || v === '') return f ? '–' : '';
  switch (f) {
    case 'mmss': return fmt.mmss(v);
    case 'pct': return fmt.pct(v);
    case 'signed': return fmt.signed(v);
    case 'signed0': return fmt.signed0(v);
    case '1': return fmt.dec(v, 1);
    case '2': return fmt.dec(v, 2);
    case 'int': return fmt.int(v);
    case 'date': return fmt.date(v);
    default: return typeof v === 'number' && !Number.isInteger(v) ? fmt.dec(v, 2) : String(v);
  }
}

/**
 * Tabla ordenable.
 * columns: [{key, label, fmt, num, render(row)->Node|string, sort(row)->value, wrap, title}]
 */
export function dataTable(columns, rows, opts = {}) {
  let sortKey = opts.sortKey ?? null, asc = opts.asc ?? false;
  const wrap = el('div', { class: 'tablewrap', style: opts.maxHeight ? { maxHeight: opts.maxHeight } : null });
  const table = el('table', { class: 'data' });
  if (opts.label) table.setAttribute('aria-label', opts.label);
  wrap.append(table);
  const sortVal = (c, r) => c.sort ? c.sort(r) : r[c.key];
  // columna que hace de enlace accesible cuando la fila es clicable
  const linkKey = opts.linkKey ?? (columns.find(c => ['name', 'pname'].includes(c.key)) || columns[0])?.key;
  let more = null;
  const allColumns = columns;
  const isEmpty = v => v == null || v === '' || (typeof v === 'number' && !isFinite(v));
  function render() {
    table.innerHTML = '';
    more?.remove(); more = null;
    // opts.hideEmpty: oculta las columnas sin ningún valor en las filas actuales
    columns = opts.hideEmpty && rows.length ? allColumns.filter(c => c.keep || rows.some(r => !isEmpty(sortVal(c, r)))) : allColumns;
    wrap.hiddenColumns = allColumns.length - columns.length;
    const thead = el('thead');
    const tr = el('tr');
    for (const c of columns) {
      const isNum = c.num ?? (rows.length && typeof sortVal(c, rows[0]) === 'number');
      const sortable = c.sortable !== false;
      const sorted = sortKey === c.key;
      const th = el('th', { scope: 'col', class: [sortable ? 'sortable' : '', isNum ? 'num' : '', sorted ? 'sorted' : '', sorted && asc ? 'asc' : '', c.wrap ? 'wrap' : ''].join(' '), title: c.title || null,
        'aria-sort': sortable ? (sorted ? (asc ? 'ascending' : 'descending') : 'none') : null });
      if (sortable) {
        th.append(el('button', { type: 'button', class: 'sort', onclick: () => {
          if (sortKey === c.key) asc = !asc; else { sortKey = c.key; asc = !isNum; }
          render();
          table.querySelector(`th[data-key="${CSS.escape(String(c.key))}"] button`)?.focus();
        } }, c.label || el('span', { class: 'sr-only' }, 'columna')));
        th.dataset.key = c.key;
      } else th.append(c.label || '');
      tr.append(th);
    }
    thead.append(tr);
    table.append(thead);
    let data = rows.slice();
    if (sortKey) {
      const c = columns.find(c => c.key === sortKey);
      if (c) data.sort((a, b) => {
        const x = sortVal(c, a), y = sortVal(c, b);
        if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
        const r = typeof x === 'string' ? x.localeCompare(y, 'es') : x - y;
        return asc ? r : -r;
      });
    }
    const tbody = el('tbody');
    const limit = opts.limit || 2000;
    if (!data.length) tbody.append(el('tr', {}, el('td', { class: 'empty-row', colspan: columns.length }, opts.emptyText || 'Sin resultados')));
    for (const r of data.slice(0, limit)) {
      const row = el('tr', { class: opts.onRowClick ? 'clickable' : '' });
      if (opts.onRowClick) row.addEventListener('click', e => { if (!e.target.closest('a, button, input, select, textarea')) opts.onRowClick(r); });
      for (const c of columns) {
        let v = c.render ? c.render(r) : formatValue(r[c.key], c.fmt);
        if (opts.onRowClick && c.key === linkKey) v = el('button', { type: 'button', class: 'linkbtn', onclick: () => opts.onRowClick(r) }, v);
        const isNum = c.num ?? typeof r[c.key] === 'number';
        const td = el('td', { class: (isNum ? 'num ' : '') + (c.wrap ? 'wrap ' : '') + (c.cellClass ? c.cellClass(r) || '' : '') }, v);
        row.append(td);
      }
      tbody.append(row);
    }
    table.append(tbody);
    wrap.classList.toggle('scroll', !opts.maxHeight && data.length > 25);
    if (data.length > limit) { more = el('div', { class: 'muted small' }, `Mostrando ${limit} de ${data.length}`); wrap.append(more); }
  }
  render();
  wrap.update = newRows => { rows = newRows; render(); };
  return wrap;
}

export function csvDownload(name, columns, rows) {
  const esc = v => { let s = v == null ? '' : String(v); if (typeof v === 'string' && /^[=+\-@\t\r]/.test(s)) s = "'" + s; return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const lines = [columns.map(c => esc(c.label)).join(';')];
  for (const r of rows) lines.push(columns.map(c => esc(c.csv ? c.csv(r) : r[c.key])).join(';'));
  downloadBlob(name, new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' }));
}

export function downloadBlob(name, blob) {
  const a = el('a', { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

let toastTimer;
export function toast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast' + (isError ? ' error' : ''); t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), isError ? 7000 : 3500);
}

export function spinner(text = 'Cargando…') { return el('div', { class: 'empty', role: 'status' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', text); }

/** Bloque de error común con botón «Reintentar». */
export function errorBox(message, onRetry, title = 'No se pudo cargar') {
  return el('div', { class: 'panel error-box', role: 'alert' }, el('h3', {}, title), el('p', {}, message),
    onRetry ? el('button', { type: 'button', onclick: onRetry }, 'Reintentar') : null);
}

/** Lee un token de color de :root (las gráficas y el mapa comparten la paleta del CSS). */
export function cssVar(name, fallback = '') {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** Titular de cartel: una palabra destacada en etiqueta naranja (estilo «City Never Sleeps»). */
export function headline(before, highlight, after = '') {
  return el('h2', { class: 'headline' }, before, el('mark', { class: 'tag-word' }, highlight), after || null);
}

export const store = {
  get(k, d) { try { const v = localStorage.getItem('dls.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('dls.' + k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};

export function teamTag(team, names) {
  return el('span', { class: `tag t${team}` }, names ? names[team] : `Equipo ${team}`);
}

/**
 * Escala de color por percentil: devuelve una función valor -> clase `cs cs-0..4`
 * (0 = peor, 4 = mejor). Con menos de 3 valores no colorea.
 */
export function scaler(values, higherBetter = true) {
  const v = values.filter(x => x != null && isFinite(x)).sort((a, b) => a - b);
  return x => {
    if (x == null || !isFinite(x) || v.length < 3) return '';
    let lo = 0; while (lo < v.length && v[lo] < x) lo++;
    const b = Math.min(4, Math.floor((lo / (v.length - 1)) * 4.999));
    return 'cs cs-' + (higherBetter ? b : 4 - b);
  };
}

/** Barra horizontal 0..max con el valor al lado. */
export function meter(value, max, { label, cls = '', text } = {}) {
  const pct = value == null || !max ? 0 : Math.max(0, Math.min(100, 100 * value / max));
  return el('span', { class: 'meter ' + cls, title: label || null },
    el('span', { class: 'meter-track', 'aria-hidden': 'true' }, el('span', { class: 'meter-fill', style: { width: pct + '%' } })),
    el('span', { class: 'meter-val' }, text ?? (value == null ? '–' : String(value))));
}

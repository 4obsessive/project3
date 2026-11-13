// Explorer for ALL the fields of a match: tree, search, automatic tables built from
// the JSON lists and charts for numeric lists.
import { el, fmt, dataTable, spinner, csvDownload } from '../util.js';
import { lines } from '../charts.js';

const isObj = v => v && typeof v === 'object' && !Array.isArray(v);
const isPrim = v => v === null || typeof v !== 'object';

export async function renderExplorer(root, matchId) {
  root.append(spinner('Downloading the full JSON…'));
  const data = await fetch(`/api/matches/${matchId}/raw`).then(r => r.json());
  root.innerHTML = '';
  let path = [];
  const search = el('input', { type: 'search', 'aria-label': 'Search the match JSON', placeholder: 'Search field or value (e.g. "heal", "midboss", "Koth")', style: { minWidth: '320px' } });
  const crumbs = el('div', { class: 'crumbs' });
  const tree = el('div', { class: 'tree' });
  const view = el('div');
  const tablesList = el('div', { class: 'tree' });
  root.append(el('div', { class: 'row' }, search), el('div', { class: 'split', style: { marginTop: '10px' } },
    el('div', {}, el('h4', {}, 'Automatic tables (lists of objects)'), tablesList, el('h4', { style: { marginTop: '10px' } }, 'Tree'), tree),
    el('div', {}, crumbs, view)));

  const get = p => p.reduce((o, k) => (o == null ? undefined : o[k]), data);
  // todas las listas de objetos (se toma el primer elemento de las listas anidadas como ejemplo)
  const lists = [];
  (function walk(v, p, depth) {
    if (depth > 6) return;
    if (Array.isArray(v)) {
      if (v.length && isObj(v[0])) { lists.push({ path: p, n: v.length }); walk(v[0], [...p, 0], depth + 1); }
      return;
    }
    if (isObj(v)) for (const [k, x] of Object.entries(v)) walk(x, [...p, k], depth + 1);
  })(data, [], 0);
  for (const l of lists) tablesList.append(el('div', { onclick: () => go(l.path) }, `${l.path.join('.')} [${l.n}]`));

  function go(p) { path = p; draw(); }
  function drawTree() {
    tree.innerHTML = '';
    const v = get(path);
    if (path.length) tree.append(el('div', { onclick: () => go(path.slice(0, -1)) }, '↑ ..'));
    const entries = Array.isArray(v) ? v.slice(0, 300).map((x, i) => [i, x]) : isObj(v) ? Object.entries(v) : [];
    for (const [k, x] of entries) {
      const desc = Array.isArray(x) ? `[${x.length}]` : isObj(x) ? '{…}' : JSON.stringify(x);
      tree.append(el('div', { onclick: () => !isPrim(x) && go([...path, k]), class: isPrim(x) ? 'muted' : '' }, `${k}: ${String(desc).slice(0, 60)}`));
    }
  }
  function draw() {
    crumbs.innerHTML = '';
    crumbs.append(el('a', { onclick: () => go([]) }, 'match'));
    path.forEach((k, i) => crumbs.append(' › ', el('a', { onclick: () => go(path.slice(0, i + 1)) }, k)));
    drawTree();
    view.innerHTML = '';
    const v = get(path);
    if (Array.isArray(v) && v.length && isObj(v[0])) {
      const keys = [...new Set(v.slice(0, 200).flatMap(o => Object.keys(o)))];
      const cols = keys.map(k => ({
        key: k, label: k,
        sort: r => isPrim(r[k]) ? r[k] : (Array.isArray(r[k]) ? r[k].length : null),
        render: r => isPrim(r[k]) ? (r[k] === null ? '–' : typeof r[k] === 'number' && !Number.isInteger(r[k]) ? fmt.dec(r[k], 3) : String(r[k]))
          : el('a', { onclick: e => { e.stopPropagation(); go([...path, v.indexOf(r), k]); } }, Array.isArray(r[k]) ? `[${r[k].length}]` : '{…}'),
      }));
      view.append(el('div', { class: 'row' }, el('b', {}, `${v.length} rows · ${keys.length} columns`),
        el('button', { onclick: () => csvDownload(`${matchId}_${path.join('_')}.csv`, keys.filter(k => v.some(o => isPrim(o[k]))).map(k => ({ key: k, label: k })), v) }, 'CSV')),
        dataTable(cols, v.map(x => x), { maxHeight: '70vh', onRowClick: r => go([...path, v.indexOf(r)]) }));
      // columnas numéricas -> gráfica rápida
      const numKeys = keys.filter(k => v.every(o => typeof o[k] === 'number'));
      if (numKeys.length && v.length > 2) {
        const pick = el('select', {}, numKeys.map(k => el('option', {}, k)));
        const chart = el('div');
        const xKey = numKeys.find(k => /time|_s$|stamp/.test(k));
        const plot = () => { chart.innerHTML = ''; chart.append(lines({ series: [{ name: pick.value, points: v.map((o, i) => [xKey ? o[xKey] : i, o[pick.value]]) }], xfmt: t => xKey ? fmt.mmss(t) : String(Math.round(t)) })); };
        pick.addEventListener('change', plot);
        view.append(el('h4', { style: { marginTop: '12px' } }, 'Single-column chart', xKey ? ` (X axis: ${xKey})` : ''), pick, chart);
        plot();
      }
    } else if (Array.isArray(v) && v.every(x => typeof x === 'number')) {
      const n = v.length, sum = v.reduce((a, b) => a + b, 0);
      view.append(el('div', { class: 'muted' }, `${n} numbers · min ${Math.min(...v)} · max ${Math.max(...v)} · mean ${fmt.dec(sum / Math.max(n, 1))}`),
        lines({ series: [{ name: path.at(-1), points: v.map((x, i) => [i, x]) }], xfmt: t => String(Math.round(t)) }),
        el('details', {}, el('summary', {}, 'Values'), el('pre', { class: 'small' }, JSON.stringify(v))));
    } else if (isObj(v) || Array.isArray(v)) {
      const rows = (Array.isArray(v) ? v.map((x, i) => [i, x]) : Object.entries(v)).map(([k, x]) => ({ k, x }));
      view.append(dataTable([
        { key: 'k', label: 'Field' },
        { key: 'x', label: 'Value', sortable: false, wrap: true, render: r => isPrim(r.x) ? String(r.x) : el('a', { onclick: () => go([...path, r.k]) }, Array.isArray(r.x) ? `list [${r.x.length}]` : 'object {…}') },
      ], rows));
    } else {
      view.append(el('pre', {}, JSON.stringify(v, null, 2)));
    }
  }
  // búsqueda en claves y valores
  search.addEventListener('change', () => {
    const q = search.value.trim().toLowerCase();
    if (!q) return draw();
    const hits = [];
    (function walk(v, p) {
      if (hits.length > 300) return;
      if (Array.isArray(v)) {
        // en listas largas de objetos basta con mirar el primer elemento para las claves
        v.forEach((x, i) => { if (i < 3 || isPrim(x)) walk(x, [...p, i]); });
      } else if (isObj(v)) {
        for (const [k, x] of Object.entries(v)) {
          if (k.toLowerCase().includes(q)) hits.push([...p, k]);
          walk(x, [...p, k]);
        }
      } else if (v != null && String(v).toLowerCase().includes(q)) hits.push(p);
    })(data, []);
    view.innerHTML = '';
    view.append(el('h4', {}, `${hits.length} matches for "${q}"`));
    for (const h of hits.slice(0, 300)) {
      const val = get(h);
      view.append(el('div', { class: 'tree' }, el('div', { onclick: () => go(isPrim(val) ? h.slice(0, -1) : h) }, `${h.join('.')} = ${isPrim(val) ? JSON.stringify(val) : Array.isArray(val) ? `[${val.length}]` : '{…}'}`)));
    }
  });
  draw();
}

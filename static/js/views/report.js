import { api, getHeroes } from '../api.js';
import { el, fmt, dataTable, toast, spinner, store, errorBox, headline } from '../util.js';
import { renderSection, setLanes } from '../blocks.js';
import { heroPortrait } from '../art.js';

export async function render(root, ctx) {
  const teams = await api.get('/api/teams');
  const saved = store.get('report', { team: '', extra: '', ids: '', window: 90, normalize: true });
  if (ctx.query.team) saved.team = ctx.query.team;
  const teamSel = el('select', {}, el('option', { value: '' }, '— solo cuentas extra —'), teams.map(t => el('option', { value: t.team, selected: t.team === saved.team }, `${t.team} (${t.players.length})`)));
  const extra = el('input', { value: saved.extra, placeholder: 'cuentas extra separadas por comas', style: { minWidth: '280px' } });
  const ids = el('textarea', { 'aria-label': 'IDs de partida', placeholder: 'IDs de partida (uno por línea o separados por comas)' }, saved.ids);
  const win = el('input', { type: 'number', value: saved.window, min: 10, max: 600, style: { width: '70px' } });
  const norm = el('input', { type: 'checkbox', checked: saved.normalize });
  const minP = el('input', { type: 'number', value: 3, min: 1, max: 6, style: { width: '50px' } });
  const days = el('input', { type: 'number', value: 60, min: 1, max: 365, style: { width: '60px' } });
  const recentBox = el('div');
  const out = el('div');
  let overrides = {};

  const parseIds = () => [...new Set(ids.value.split(/[\s,;]+/).map(x => x.trim()).filter(x => /^\d+$/.test(x)))];
  const persist = () => store.set('report', { team: teamSel.value, extra: extra.value, ids: ids.value, window: +win.value, normalize: norm.checked });

  async function findRecent() {
    recentBox.innerHTML = ''; recentBox.append(spinner('Buscando en el historial de partidas de la plantilla…'));
    try {
      const q = new URLSearchParams({ team: teamSel.value, extra: extra.value, min_players: minP.value, days: days.value });
      const r = await api.get('/api/teams/recent-matches?' + q);
      recentBox.innerHTML = '';
      const chosen = new Set(parseIds());
      recentBox.append(el('div', { class: 'muted small' }, `${r.matches.length} partidas con ≥${minP.value} cuentas de la plantilla (${r.roster_accounts} cuentas) en el mismo equipo` + (r.errors.length ? ` · ${r.errors.length} cuentas sin historial` : '')),
        el('div', { class: 'row' },
          el('button', { onclick: () => { ids.value = r.matches.map(m => m.match_id).join('\n'); persist(); toast(`${r.matches.length} partidas añadidas`); } }, 'Usar todas'),
          el('button', { onclick: () => { ids.value = r.matches.slice(0, 20).map(m => m.match_id).join('\n'); persist(); } }, 'Usar las 20 más recientes')),
        dataTable([
          { key: 'add', label: '', sortable: false, render: m => { const c = el('input', { type: 'checkbox', 'aria-label': `Usar partida ${m.match_id}`, checked: chosen.has(String(m.match_id)) }); c.addEventListener('change', () => { const s = new Set(parseIds()); c.checked ? s.add(String(m.match_id)) : s.delete(String(m.match_id)); ids.value = [...s].join('\n'); persist(); }); return c; } },
          { key: 'match_id', label: 'Partida' }, { key: 'start_time', label: 'Fecha', fmt: 'date' }, { key: 'duration_s', label: 'Duración', fmt: 'mmss' },
          { key: 'side', label: 'Lado', render: m => el('span', { class: `tag t${m.side}` }, ctx.teamNames[m.side]) },
          { key: 'roster_players', label: 'De la plantilla' }, { key: 'won', label: 'Resultado', render: m => m.won ? 'Victoria' : 'Derrota' },
          { key: 'stored', label: 'Guardada', render: m => m.stored ? 'sí' : '' },
        ], r.matches, { sortKey: 'start_time', maxHeight: '300px' }));
    } catch (e) { recentBox.innerHTML = ''; recentBox.append(errorBox(e.message, findRecent, 'No se pudieron buscar partidas')); }
  }

  async function run() {
    persist();
    const list = parseIds();
    if (!list.length) return toast('Indica al menos una partida', true);
    out.innerHTML = ''; out.append(spinner(`Analizando ${list.length} partidas (las que no estén guardadas se descargan)…`));
    try {
      const r = await api.post('/api/report', {
        team: teamSel.value, extra_accounts: extra.value.split(/[\s,;]+/).filter(Boolean), match_ids: list, side_overrides: overrides,
        params: { midboss_window_s: +win.value, normalize: norm.checked },
      });
      show(r);
    } catch (e) { out.innerHTML = ''; out.append(errorBox(e.message, run, 'No se pudo generar el informe')); }
  }

  async function heroStrip(r) {
    if (!(r.our_heroes || []).length) return null;
    let heroes = [];
    try { heroes = await getHeroes(); } catch (e) { /* sin catálogo: se muestran las iniciales */ }
    const byId = new Map(heroes.map(h => [h.id, h]));
    return el('div', { class: 'report-heroes tilt-cards', role: 'group', 'aria-label': 'Héroes del equipo en las partidas analizadas' },
      r.our_heroes.map(o => {
        const h = byId.get(o.hero_id) || { id: o.hero_id, name: `#${o.hero_id}` };
        return el('span', { title: `${h.name}: ${o.matches} partidas` },
          heroPortrait(h, { size: 'md', shape: 'card' }), el('b', {}, `×${o.matches}`));
      }));
  }

  function show(r) {
    out.innerHTML = '';
    setLanes(r.lanes);
    const TN = r.team_names;
    const head = el('div', { class: 'panel' },
      headline('Informe de ', r.team || 'cuentas extra'),
      el('div', { class: 'muted' }, `${r.n} partidas analizadas · plantilla de ${r.roster_size} cuentas · ventana Midboss ${r.params.midboss_window_s} s · ${r.params.normalize ? 'lado normalizado' : 'sin normalizar'}`),
      r.team_names_verified ? null : el('div', { class: 'muted small' }, 'Nombres de lado (equipo 0 = Hidden King, 1 = Archmother) según fuentes de terceros; que el equipo 0 tiene la base abajo está verificado.'),
      r.load_errors.length ? el('div', { class: 'note warning block' }, el('span', { class: 'lbl' }, 'aviso'), 'No se pudieron cargar: ' + r.load_errors.map(e => `${e.match_id} (${e.error})`).join(' · ')) : null);
    // lados detectados con corrección manual
    const sideRows = r.sides.map(s => ({ ...s }));
    head.append(el('details', { open: r.skipped.length > 0 }, el('summary', {}, `Lado por partida (${r.skipped.length} sin detectar)`),
      dataTable([
        { key: 'match_id', label: 'Partida' },
        { key: 'counts', label: 'Plantilla en 0 / 1', render: s => `${s.roster_counts[0]} / ${s.roster_counts[1]}` },
        { key: 'auto', label: 'Detectado', render: s => s.auto == null ? '—' : TN[s.auto] },
        { key: 'side', label: 'Usado', render: s => {
          const sel = el('select', { 'aria-label': `Lado de la partida ${s.match_id}` }, el('option', { value: '' }, 'auto'), [0, 1].map(t => el('option', { value: t, selected: s.source === 'manual' && s.side === t }, TN[t])));
          sel.addEventListener('change', () => { if (sel.value === '') delete overrides[s.match_id]; else overrides[s.match_id] = +sel.value; });
          return sel;
        } },
      ], sideRows),
      el('button', { onclick: run }, 'Recalcular con estos lados')));
    const toc = el('nav', { class: 'toc no-print', 'aria-label': 'Índice del informe' }, el('ol', {}, r.sections.map(s => el('li', {}, el('button', { type: 'button', class: 'linkbtn', onclick: () => { const t = document.getElementById('sec-' + s.id); if (t) { t.tabIndex = -1; t.scrollIntoView({ behavior: 'smooth' }); t.focus({ preventScroll: true }); } } }, s.title)))));
    head.append(toc, el('button', { class: 'no-print', onclick: () => window.print() }, 'Imprimir / PDF'));
    out.append(head, ...r.sections.map(renderSection));
    // los retratos se insertan bajo la línea de resumen cuando llega el catálogo de héroes
    heroStrip(r).then(strip => { if (strip && head.isConnected) head.children[1].after(strip); });
  }

  root.append(el('div', { class: 'panel no-print' },
    el('h3', {}, 'Informe estadístico de un equipo'),
    el('p', { class: 'muted small' }, 'Analiza N partidas en conjunto. El lado de cada partida se detecta por qué jugadores de la plantilla hay en cada equipo; se puede corregir a mano. Lo que la API no da se marca como «no disponible».'),
    el('div', { class: 'row' }, el('label', {}, 'Equipo', teamSel), el('label', {}, 'Cuentas extra', extra)),
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { onclick: findRecent }, 'Buscar partidas recientes del equipo'),
      el('label', {}, 'mín. jugadores juntos', minP), el('label', {}, 'últimos', days, 'días')),
    recentBox,
    el('div', { style: { marginTop: '8px' } }, ids),
    el('div', { class: 'row', style: { marginTop: '8px' } },
      el('label', {}, 'Ventana de kills antes del Midboss (s)', win),
      el('label', {}, norm, 'normalizar lado (base propia abajo)'),
      el('button', { class: 'primary', onclick: () => { overrides = {}; run(); } }, 'Generar informe'))), out);
}

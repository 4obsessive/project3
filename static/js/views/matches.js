import { api, getHeroes } from '../api.js';
import { el, fmt, dataTable, toast, spinner, csvDownload, store, errorBox } from '../util.js';
import { MapView, COLORS, legend, loadMapInfo } from '../map.js';
import { timeline } from '../charts.js';
import { renderExplorer } from './explorer.js';
import { openProfile } from './profile.js';
import { icon } from '../icons.js';
import { heroPortrait, objectiveImg, laneStyle } from '../art.js';
import { matchRow } from './home.js';

export async function render(root, ctx) {
  const idInput = el('input', { id: 'match-id', inputmode: 'numeric', placeholder: 'ID de partida', 'aria-label': 'ID de partida', style: { width: '140px' } });
  const fileInput = el('input', { type: 'file', id: 'match-file', class: 'sr-only', accept: '.json,application/json' });
  const list = el('div');
  const detail = el('div');
  const load = async () => {
    const id = idInput.value.trim();
    if (!id) return;
    btn.disabled = true; btn.textContent = 'Descargando…';
    try { await api.post('/api/matches/load', { match_id: id }); await refresh(); location.hash = `#partidas/${id}`; }
    catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; btn.textContent = 'Cargar'; }
  };
  const btn = el('button', { class: 'primary', onclick: load }, 'Cargar');
  idInput.addEventListener('keydown', e => { if (e.key === 'Enter') load(); });
  fileInput.addEventListener('change', async () => {
    const f = fileInput.files[0]; if (!f) return;
    try { const r = await api.post('/api/matches/upload', await f.text()); toast(`Partida ${r.match_id} guardada`); await refresh(); location.hash = `#partidas/${r.match_id}`; }
    catch (e) { toast(e.message, true); }
    fileInput.value = '';
  });
  root.append(el('div', { class: 'split' },
    el('div', {},
      el('div', { class: 'panel' }, el('h3', {}, 'Cargar partida'), el('div', { class: 'row' }, idInput, btn),
        el('div', { class: 'muted small', style: { margin: '10px 0 4px' } }, 'o sube su JSON (metadata de deadlock-api):'),
        el('label', { for: 'match-file', class: 'filepick' }, icon('upload'), el('span', {}, 'Elegir archivo JSON…')), fileInput),
      el('div', { class: 'panel' }, el('h3', {}, 'Guardadas'), list)),
    detail));

  async function refresh() {
    const ms = await api.get('/api/matches');
    list.innerHTML = '';
    if (!ms.length) list.append(el('div', { class: 'muted small' }, 'Ninguna todavía.'));
    for (const m of ms) {
      list.append(matchRow(m));
    }
  }
  await refresh();
  const id = ctx.params[0];
  if (id) showMatch(detail, id, ctx);
  else detail.append(el('div', { class: 'panel empty' }, icon('partidas', 'big'), el('p', {}, 'Elige una partida guardada o carga una nueva por ID para ver su marcador, la diferencia de oro y el minimapa.')));
}

async function showMatch(root, id, ctx) {
  root.innerHTML = ''; root.append(spinner('Cargando partida…'));
  let m;
  try { m = await api.get(`/api/matches/${id}`); } catch (e) { root.innerHTML = ''; root.append(errorBox(e.message, () => showMatch(root, id, ctx), 'No se pudo cargar la partida')); return; }
  try { const hs = await getHeroes(); heroById = new Map(hs.map(h => [h.id, h])); } catch { heroById = new Map(); }
  root.innerHTML = '';
  const TN = m.team_names;
  const tname = t => `${TN[t]} (${t})`;
  const verified = m.team_names_verified ? '' : ' · nombres de lado según fuentes de terceros (equipo 0 = base abajo, verificado)';
  const head = scoreboard(m, TN, verified);
  const gold = goldPanel(m, tname);
  const tabs = el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Secciones de la partida' });
  const body = el('div', { class: 'panel', role: 'tabpanel', id: 'match-tabpanel', tabindex: '0' });
  root.append(head, gold, tabs, body);
  const views = {
    'Resumen': () => resumen(body, m, tname, ctx),
    'Objetivos': () => objetivos(body, m, tname),
    'Midboss': () => midboss(body, m, tname),
    'Minimapa': () => minimapa(body, m, tname),
    'Explorador': () => renderExplorer(body, m.match_id),
  };
  let current = store.get('matchTab', 'Resumen');
  if (!views[current]) current = 'Resumen';
  const select = b => {
    current = b.dataset.tab; store.set('matchTab', current);
    for (const x of tabs.children) { const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; }
    body.setAttribute('aria-labelledby', b.id);
    body.innerHTML = ''; views[current]();
  };
  for (const name of Object.keys(views)) {
    const on = name === current;
    const b = el('button', { type: 'button', role: 'tab', id: 'tab-' + name.toLowerCase(), 'aria-controls': 'match-tabpanel', 'aria-selected': String(on), tabindex: on ? '0' : '-1', class: on ? 'active' : '', onclick: () => select(b) }, name);
    b.dataset.tab = name;
    tabs.append(b);
  }
  // flechas para moverse entre pestañas (patrón ARIA tabs)
  tabs.addEventListener('keydown', e => {
    const list = [...tabs.children], i = list.indexOf(document.activeElement);
    if (i < 0) return;
    const j = e.key === 'ArrowRight' ? (i + 1) % list.length : e.key === 'ArrowLeft' ? (i - 1 + list.length) % list.length : e.key === 'Home' ? 0 : e.key === 'End' ? list.length - 1 : -1;
    if (j < 0) return;
    e.preventDefault(); list[j].focus(); select(list[j]);
  });
  body.setAttribute('aria-labelledby', 'tab-' + current.toLowerCase());
  views[current]();
}

let heroById = new Map();
/** Retrato del héroe de un jugador de la partida (con los datos de /api/heroes si hay). */
const portrait = (p, opts) => heroPortrait(heroById.get(p.hero_id) || { id: p.hero_id, name: p.hero }, opts);
const pname = p => p.name || `Cuenta ${p.account_id}`;
const kdaRatio = p => (p.kills + p.assists) / Math.max(1, p.deaths);
function mvpOf(m) {
  const r1 = m.players.find(p => p.mvp_rank === 1);
  if (r1) return r1;
  return m.players.slice().sort((a, b) => kdaRatio(b) * b.net_worth - kdaRatio(a) * a.net_worth)[0];
}
const teamSum = (m, t, k) => m.players.filter(p => p.team === t).reduce((a, p) => a + (p[k] || 0), 0);

function scoreboard(m, TN, verified) {
  const side = t => el('div', { class: `bside t${t}` + (m.winning_team === t ? ' won' : '') },
    el('div', { class: 'bstrip' }, m.players.filter(p => p.team === t).sort((x, y) => y.net_worth - x.net_worth).slice(0, 6)
      .map(p => el('span', { class: 'bcell', title: `${p.hero} · ${pname(p)}` }, portrait(p, { size: 'md', shape: 'card' })))),
    el('div', { class: 'blabel' },
      el('div', { class: 'bname' }, el('span', { class: `tag t${t}` }, `Equipo ${t}`), el('b', {}, TN[t])),
      el('div', { class: 'bmeta' }, `${fmt.int(teamSum(m, t, 'net_worth'))} oro · `, m.winning_team === t ? el('span', { class: 'sb-win' }, icon('trophy'), 'Victoria') : el('span', { class: 'sb-lose' }, 'Derrota'))));
  return el('section', { class: 'panel scoreboard', 'aria-label': 'Marcador' },
    el('div', { class: 'sb-top' },
      el('h2', {}, `Partida #${m.match_id}`),
      el('button', { type: 'button', class: 'danger small-btn', onclick: async () => { if (!confirm('¿Borrar la partida guardada?')) return; try { await api.post(`/api/matches/${m.match_id}/delete`); location.hash = '#partidas'; } catch (e) { toast(e.message, true); } } }, 'Borrar')),
    el('div', { class: 'hero-banner' }, side(0),
      el('div', { class: 'bcenter' },
        el('div', { class: 'sb-vs' }, 'KILLS · DURACIÓN'),
        el('div', { class: 'bscore', 'aria-label': `${teamSum(m, 0, 'kills')} a ${teamSum(m, 1, 'kills')}` },
          el('span', { class: 't0' }, String(teamSum(m, 0, 'kills'))), ' : ', el('span', { class: 't1' }, String(teamSum(m, 1, 'kills')))),
        el('div', { class: 'sb-dur' }, fmt.mmss(m.duration_s)), el('div', { class: 'muted small' }, fmt.datetime(m.start_time))),
      side(1)),
    verified ? el('div', { class: 'muted small', style: { padding: '8px 16px' } }, verified.replace(/^ · /, '')) : null);
}

/** Diferencia de oro (equipo 0 − equipo 1) con los momentos clave (objetivos y Midboss). */
function goldPanel(m, tname) {
  const box = el('section', { class: 'panel gold' }, el('div', { class: 'section-head' }, el('h3', {}, 'Diferencia de oro'),
    el('div', { class: 'legend' }, el('span', {}, el('i', { style: { background: 'var(--t0)' } }), `ventaja ${tname(0)}`), el('span', {}, el('i', { style: { background: 'var(--t1)' } }), `ventaja ${tname(1)}`))));
  const times = [...new Set(m.players.flatMap(p => (p.nw_timeline || []).map(x => x[0])))].sort((a, b) => a - b);
  if (times.length < 2) { box.append(el('p', { class: 'muted small' }, 'La partida no trae la evolución del net worth.')); return box; }
  const at = (p, t) => { const tl = p.nw_timeline || []; let v = 0; for (const [s, nw] of tl) { if (s <= t) v = nw; else break; } return v; };
  const pts = [[0, 0], ...times.map(t => [t, m.players.reduce((a, p) => a + (p.team === 0 ? 1 : -1) * at(p, t), 0)])];
  const W = 900, H = 200, pad = { l: 46, r: 10, t: 12, b: 34 };
  const T = Math.max(m.duration_s || 0, times[times.length - 1]);
  const maxAbs = Math.max(1000, ...pts.map(p => Math.abs(p[1])));
  const x = t => pad.l + (W - pad.l - pad.r) * t / T, y = v => pad.t + (H - pad.t - pad.b) * (1 - (v + maxAbs) / (2 * maxAbs));
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'goldchart'); svg.setAttribute('role', 'img');
  const final = pts[pts.length - 1][1];
  svg.setAttribute('aria-label', `Diferencia de oro a lo largo de la partida; al final ${fmt.signed0(final)} para ${final >= 0 ? tname(0) : tname(1)}`);
  const mk = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; svg.append(e); return e; };
  const line = pts.map(([t, v], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${line}L${x(pts[pts.length - 1][0])},${y(0)}L${x(0)},${y(0)}Z`;
  const clip = (id, y0, h) => { const d = mk('clipPath', { id }); const r = document.createElementNS(ns, 'rect'); r.setAttribute('x', 0); r.setAttribute('y', y0); r.setAttribute('width', W); r.setAttribute('height', h); d.append(r); };
  const uid = 'g' + m.match_id;
  clip(uid + 'a', 0, y(0)); clip(uid + 'b', y(0), H);
  for (const v of [maxAbs, maxAbs / 2, 0, -maxAbs / 2, -maxAbs]) {
    mk('line', { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: v === 0 ? 'zero' : 'gridl' });
    mk('text', { x: pad.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, v === 0 ? '0' : (v > 0 ? '+' : '−') + Math.round(Math.abs(v) / 1000) + 'k');
  }
  for (let mn = 0; mn * 60 <= T; mn += 5) mk('text', { x: x(mn * 60), y: H - 18, 'text-anchor': 'middle' }, mn + "'");
  mk('path', { d: area, class: 'area t0', 'clip-path': `url(#${uid}a)` });
  mk('path', { d: area, class: 'area t1', 'clip-path': `url(#${uid}b)` });
  mk('path', { d: line, class: 'gline' });
  // momentos clave en el eje inferior
  const ev = [
    ...m.objectives.filter(o => o.destroyed_s).map(o => ({ t: o.destroyed_s, team: o.destroyed_by, label: `${fmt.mmss(o.destroyed_s)} · ${tname(o.destroyed_by ?? (1 - o.owner_team))} destruye ${o.label}`, kind: o.type })),
    ...m.midboss.map(b => ({ t: b.t, team: b.team_claimed, label: `${fmt.mmss(b.t)} · Midboss: lo reclama ${tname(b.team_claimed)}`, kind: 'Midboss' })),
  ];
  for (const e of ev) {
    const g = mk('g', { class: `moment t${e.team}` + (e.kind === 'Midboss' ? ' boss' : '') });
    const big = /Midboss|Patron|Core|Shrine|Titan/i.test(e.kind || '');
    const c = document.createElementNS(ns, big ? 'rect' : 'circle');
    if (big) { c.setAttribute('x', x(e.t) - 4.5); c.setAttribute('y', H - 9 - 4.5); c.setAttribute('width', 9); c.setAttribute('height', 9); c.setAttribute('transform', `rotate(45 ${x(e.t)} ${H - 9})`); }
    else { c.setAttribute('cx', x(e.t)); c.setAttribute('cy', H - 9); c.setAttribute('r', 3.5); }
    const tt = document.createElementNS(ns, 'title'); tt.textContent = e.label;
    g.append(c, tt);
    if (big) { const l = document.createElementNS(ns, 'line'); l.setAttribute('x1', x(e.t)); l.setAttribute('x2', x(e.t)); l.setAttribute('y1', pad.t); l.setAttribute('y2', H - pad.b); l.setAttribute('class', 'mline'); g.prepend(l); }
  }
  const peak0 = pts.reduce((a, p) => p[1] > a[1] ? p : a), peak1 = pts.reduce((a, p) => p[1] < a[1] ? p : a);
  box.append(el('div', { class: 'chart-scroll' }, svg),
    el('div', { class: 'gold-facts' },
      el('span', {}, 'Final: ', el('b', {}, fmt.signed0(final)), ` para ${final >= 0 ? tname(0) : tname(1)}`),
      el('span', {}, `Máx. ${tname(0)}: `, el('b', {}, fmt.signed0(peak0[1])), ` (${fmt.mmss(peak0[0])})`),
      el('span', {}, `Máx. ${tname(1)}: `, el('b', {}, fmt.signed0(-peak1[1])), ` (${fmt.mmss(peak1[0])})`),
      el('span', { class: 'muted' }, '● objetivo · ◆ Midboss/estructura grande (pasa el ratón para ver detalle)')));
  return box;
}

function resumen(root, m, tname, ctx) {
  const mvp = mvpOf(m);
  const maxNW = Math.max(...m.players.map(p => p.net_worth || 0), 1);
  const maxKA = Math.max(...m.players.map(p => p.kills + p.deaths + p.assists), 1);
  const maxDmg = Math.max(...m.players.map(p => p.player_damage || 0), 1);
  const who = p => p.player_id ? el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(p.player_id, ctx) }, pname(p)) : el('span', { class: 'muted' }, pname(p));
  root.append(el('div', { class: 'mvp' }, el('span', { class: 'mvp-badge' }, icon('star'), 'MVP'),
    el('div', {}, portrait(mvp, { size: 'sm', shape: 'round' }), ' ', el('b', { class: 'mvp-hero' }, mvp.hero), ' · ', who(mvp), ' · ', el('span', { class: `tag t${mvp.team}` }, tname(mvp.team))),
    el('div', { class: 'mvp-stats' }, `${mvp.kills}/${mvp.deaths}/${mvp.assists}`, el('span', { class: 'muted' }, ` · ${fmt.int(mvp.net_worth)} oro`),
      el('span', { class: 'muted small' }, mvp.mvp_rank === 1 ? ' (según la partida)' : ' (estimado: KDA × oro)'))));
  const grid = el('div', { class: 'grid2' });
  for (const t of [0, 1]) {
    const ps = m.players.filter(p => p.team === t).sort((a, b) => b.net_worth - a.net_worth);
    const k = teamSum(m, t, 'kills'), nw = teamSum(m, t, 'net_worth');
    grid.append(el('div', { class: `team-card t${t}` },
      el('h3', {}, el('span', { class: `tag t${t}` }, tname(t)), ` ${m.winning_team === t ? 'Victoria' : 'Derrota'}`, el('span', { class: 'muted small' }, ` · ${k} kills · ${fmt.int(nw)} oro`)),
      el('ul', { class: 'plist' }, ps.map(p => el('li', { class: p === mvp ? 'is-mvp' : '' },
        el('div', { class: 'pl-who' }, portrait(p, { size: 'sm', shape: 'round' }), el('div', { class: 'pl-name' }, el('b', {}, p.hero), el('span', { class: 'small' }, who(p))), p === mvp ? el('span', { class: 'mvp-dot', title: 'MVP' }, icon('star')) : null),
        el('div', { class: 'pl-kda', title: `${p.kills} kills · ${p.deaths} muertes · ${p.assists} asistencias` },
          el('span', { class: 'kda-num' }, `${p.kills}/${p.deaths}/${p.assists}`),
          el('span', { class: 'kda-bar', 'aria-hidden': 'true', style: { width: (100 * (p.kills + p.deaths + p.assists) / maxKA) + '%' } },
            el('i', { class: 'k', style: { flex: p.kills } }), el('i', { class: 'd', style: { flex: p.deaths } }), el('i', { class: 'a', style: { flex: p.assists } }))),
        el('div', { class: 'pl-nw' }, el('span', { class: 'lbl' }, 'Oro'), el('span', { class: 'bar', 'aria-hidden': 'true' }, el('span', { style: { width: (100 * p.net_worth / maxNW) + '%' } })), el('span', { class: 'v' }, fmt.int(p.net_worth))),
        p.player_damage != null ? el('div', { class: 'pl-nw dmg' }, el('span', { class: 'lbl' }, 'Daño'), el('span', { class: 'bar', 'aria-hidden': 'true' }, el('span', { style: { width: (100 * p.player_damage / maxDmg) + '%' } })), el('span', { class: 'v' }, fmt.int(p.player_damage))) : null)))));
  }
  root.append(el('div', { class: 'legend' }, el('span', {}, el('i', { style: { background: 'var(--ok)' } }), 'kills'), el('span', {}, el('i', { style: { background: 'var(--bad)' } }), 'muertes'), el('span', {}, el('i', { style: { background: 'var(--muted)' } }), 'asistencias')), grid);
  const det = el('details', { class: 'block' }, el('summary', {}, 'Tabla completa'));
  for (const t of [0, 1]) {
    det.append(el('h4', {}, tname(t)), dataTable([
      { key: 'hero', label: 'Héroe', render: p => el('span', { class: 'hero-cell' }, portrait(p, { size: 'sm', shape: 'round' }), p.hero) },
      { key: 'name', label: 'Jugador', render: p => who(p) },
      { key: 'kills', label: 'K' }, { key: 'deaths', label: 'D' }, { key: 'assists', label: 'A' },
      { key: 'net_worth', label: 'Net worth', fmt: 'int' }, { key: 'player_damage', label: 'Daño', fmt: 'int' }, { key: 'last_hits', label: 'Last hits' }, { key: 'denies', label: 'Denies' }, { key: 'level', label: 'Nivel' },
      { key: 'comeback_gold_koth', label: 'Comeback Gold Koth', title: '> 0: ganó al menos un KOTH yendo por detrás (no es un recuento)' },
    ], m.players.filter(p => p.team === t), { sortKey: 'net_worth' }));
  }
  root.append(det);
}

function objetivos(root, m, tname) {
  root.append(el('p', { class: 'muted small' }, '«Equipo» es el DUEÑO del objetivo; lo destruye el rival. Si no cayó, se muestra el primer golpe. El mapeo de IDs es inferido (editable en Ajustes).'));
  const cols = [
    { key: 'label', label: 'Objetivo' }, { key: 'objective_id', label: 'ID' },
    { key: 'destroyed_s', label: 'Cae', fmt: 'mmss' },
    { key: 'first_damage_s', label: 'Primer golpe', render: r => r.destroyed_s ? fmt.mmss(r.first_damage_s) : (r.first_damage_s ? `${fmt.mmss(r.first_damage_s)} (no cayó)` : 'sin daño') },
    { key: 'player_damage', label: 'Daño de jugadores', fmt: 'int' }, { key: 'creep_damage', label: 'Daño de tropas', fmt: 'int' },
  ];
  root.append(laneTracks(m, tname), kothCard(m, tname));
  const grid = el('div', { class: 'grid2' });
  for (const t of [0, 1]) {
    const rows = m.objectives.filter(o => o.owner_team === t);
    grid.append(el('div', {}, el('h3', {}, 'Objetivos de ', el('span', { class: `tag t${t}` }, tname(t))), dataTable(cols, rows, { sortKey: 'destroyed_s', asc: true })));
  }
  root.append(el('div', { class: 'row' }, el('button', { onclick: () => csvDownload(`objetivos_${m.match_id}.csv`, [
    { label: 'equipo_dueño', csv: r => r.owner_team }, { label: 'objetivo', csv: r => r.label }, { label: 'id', csv: r => r.objective_id },
    { label: 'cae_s', csv: r => r.destroyed_s ?? '' }, { label: 'cae_mmss', csv: r => r.destroyed_s ? fmt.mmss(r.destroyed_s) : '' },
    { label: 'primer_golpe_s', csv: r => r.first_damage_s ?? '' }], m.objectives) }, 'Exportar CSV')), grid);
  const ev = side => m.objectives.filter(o => o.owner_team === side && o.destroyed_s).map(o => ({ t: o.destroyed_s, label: `${o.label} de ${tname(side)}`, side: side === 0 ? 't0' : 't1', kind: o.type }));
  const mb = m.midboss.map(x => ({ t: x.t, label: `Midboss: lo mata ${tname(x.team_killed)}, lo reclama ${tname(x.team_claimed)}`, side: x.team_killed === 0 ? 't0' : 't1', kind: 'Titan' }));
  root.append(el('h3', { style: { marginTop: '14px' } }, 'Línea de tiempo'),
    el('p', { class: 'muted small' }, 'Color = equipo DUEÑO del objetivo que cae (ámbar relleno = equipo 0, azul en contorno = equipo 1).'),
    timeline({ rows: [
      { label: `Pierde ${tname(0)}`, duration: m.duration_s, events: ev(0) },
      { label: `Pierde ${tname(1)}`, duration: m.duration_s, events: ev(1) },
      { label: 'Midboss', duration: m.duration_s, events: mb },
    ] }));
}

/** Una pista por carril (+ «Base») con cada objetivo destruido en su minuto, borde = equipo dueño. */
function laneTracks(m, tname) {
  const fallen = m.objectives.filter(o => o.destroyed_s);
  const dur = Math.max(m.duration_s || 0, ...fallen.map(o => o.destroyed_s), 1);
  const laneIds = [...new Set([1, 3, 4, ...fallen.map(o => o.lane).filter(l => l != null)])];
  const row = (name, alias, color, list) => el('div', { class: 'lane-row', style: { '--lane': color } },
    el('div', { class: 'ln' }, name, alias ? el('small', {}, alias) : null),
    el('div', { class: 'lane-track', role: 'list', 'aria-label': `Objetivos destruidos en ${name}` },
      list.map(o => el('span', { class: `ev t${o.owner_team}`, role: 'listitem', style: { left: (100 * o.destroyed_s / dur).toFixed(2) + '%' },
        title: `${o.type} de ${m.team_names[o.owner_team]} · ${fmt.mmss(o.destroyed_s)}` }, objectiveImg(o.type, o.owner_team, { size: 'sm' })))));
  const axis = el('div', { class: 'lane-row lane-axis', 'aria-hidden': 'true' }, el('div'),
    el('div', { class: 'lane-track' }, Array.from({ length: Math.floor(dur / 600) + 1 }, (_, i) => el('span', { class: 'tick', style: { left: (100 * i * 600 / dur) + '%' } }, `${i * 10}'`))));
  return el('div', { class: 'lane-tracks' },
    el('h3', {}, 'Objetivos por carril'),
    el('p', { class: 'muted small' }, 'Cada marca es un objetivo destruido en su minuto; el borde es el color del equipo DUEÑO (', el('span', { class: 'tag t0' }, tname(0)), el('span', { class: 'tag t1' }, tname(1)), ').'),
    laneIds.map(id => { const l = laneStyle(id, m.lanes); return row(l.nombre, l.alias, l.color, fallen.filter(o => o.lane === id)); }),
    row('Base', 'Shrines, Titan y Core', 'var(--muted)', fallen.filter(o => o.lane == null)),
    axis);
}

function kothCard(m, tname) {
  return el('div', { class: 'koth-card' },
    el('div', { class: 'koth-head' }, objectiveImg('KOTH', null, { size: 'lg' }), el('h3', {}, 'KOTH (Unstable Rift)')),
    el('div', { class: 'unavailable block' }, el('b', {}, 'No disponible: '), 'la API no trae los cash-in del KOTH.'),
    el('div', { class: 'grid2' }, [0, 1].map(t => el('div', {},
      el('h4', {}, 'Comeback Gold Koth · ', el('span', { class: `tag t${t}` }, tname(t))),
      el('ul', { class: 'koth-list' }, m.players.filter(p => p.team === t).map(p =>
        el('li', {}, portrait(p, { size: 'sm', shape: 'round' }), el('span', {}, p.hero), el('b', {}, fmt.int(p.comeback_gold_koth || 0)))))))));
}

function midboss(root, m, tname) {
  root.append(el('div', { class: 'koth-head' }, objectiveImg('Midboss', null, { size: 'lg' }), el('h3', {}, 'Midboss')),
    el('div', { class: 'note interpretation' }, el('span', { class: 'lbl' }, 'interpretación'), '«Reclamado» (team_claimed) no está documentado: si lo reclama quien no lo mató, se considera un robo.'),
    el('div', { class: 'unavailable block' }, el('b', {}, 'No disponible: '), 'cristales, quién lo inicia e intentos fallidos (la API no los registra).'),
    m.midboss.length ? dataTable([
      { key: 'n', label: '#' }, { key: 't', label: 'Minuto', fmt: 'mmss' },
      { key: 'team_killed', label: 'Lo mata', render: r => el('span', { class: `tag t${r.team_killed}` }, tname(r.team_killed)) },
      { key: 'team_claimed', label: 'Lo reclama', render: r => el('span', { class: `tag t${r.team_claimed}` }, tname(r.team_claimed)) },
      { key: 'stolen', label: '¿Robo?', render: r => r.stolen ? el('span', { class: 'hero-cell' }, objectiveImg('Rejuvenator', null, { size: 'sm' }), 'sí (interpretación)') : 'no' },
    ], m.midboss, { sortKey: 't', asc: true }) : el('p', { class: 'muted' }, 'No hubo Midboss.'));
}

async function minimapa(root, m, tname) {
  const status = el('div', {}, spinner('Decodificando posiciones…'));
  root.append(status);
  let pos, info;
  try { [pos, info] = await Promise.all([api.get(`/api/matches/${m.match_id}/positions?step=2`), loadMapInfo()]); }
  catch (e) { status.replaceWith(errorBox(e.message, () => { root.innerHTML = ''; minimapa(root, m, tname); }, 'No se pudieron cargar las posiciones')); return; }
  status.remove();
  const dur = m.duration_s, step = pos.interval_s;
  const st = { team: 'all', slot: 'all', from: 0, to: Math.ceil(dur / 60), heat: true, deaths: true, lanes: true, objImgs: false, koth: false, objectives: false, rotate: false };
  const teamSel = el('select', { 'aria-label': 'Equipo' }, [['all', 'Ambos equipos'], ['0', tname(0)], ['1', tname(1)]].map(([v, l]) => el('option', { value: v }, l)));
  const slotSel = el('select', { 'aria-label': 'Jugador' }, el('option', { value: 'all' }, 'Todos los jugadores'),
    m.players.map(p => el('option', { value: p.slot }, `${p.hero} · ${pname(p)} (${tname(p.team)})`)));
  const from = el('input', { 'aria-label': 'Desde el minuto', type: 'number', min: 0, max: st.to, value: 0, style: { width: '64px' } });
  const to = el('input', { 'aria-label': 'Hasta el minuto', type: 'number', min: 0, max: st.to, value: st.to, style: { width: '64px' } });
  const chk = (key, label) => { const c = el('input', { type: 'checkbox', checked: st[key] }); c.addEventListener('change', () => { st[key] = c.checked; draw(); }); return el('label', {}, c, label); };
  const box = el('div');
  const map = new MapView(box, { size: 820, label: `Minimapa de la partida ${m.match_id}` });
  const counts = el('div', { class: 'muted small' });
  root.append(el('div', { class: 'row' }, teamSel, slotSel, el('label', {}, 'minuto', from, '–', to), chk('heat', 'calor de posiciones'), chk('deaths', 'muertes ✕'),
    chk('lanes', 'carriles'), chk('objImgs', 'objetivos'), chk('koth', 'KOTH'), chk('objectives', 'códigos de objetivo'), chk('rotate', 'girar 180°'), el('button', { onclick: () => map.exportPNG(`minimapa_${m.match_id}.png`) }, 'Exportar PNG')),
    legend([[COLORS.t0, tname(0)], [COLORS.t1, tname(1)], [COLORS.neutral, 'muerte (color = equipo de la víctima)', 'x']]), counts, box,
    el('p', { class: 'muted small' }, `Calibración: ${info.calibration?.source || '—'}. Las posiciones con vida 0 (muerto) se descartan.`));
  for (const [i, k] of [[teamSel, 'team'], [slotSel, 'slot']]) i.addEventListener('change', () => { st[k] = i.value; draw(); });
  for (const [i, k] of [[from, 'from'], [to, 'to']]) i.addEventListener('input', () => { st[k] = +i.value; draw(); });

  function relToWorld(u, v) {
    const c = info.calibration;
    if (c.invert_x) u = 1 - u; if (c.invert_y !== false) v = 1 - v;
    return [c.x_min + u * (c.x_max - c.x_min), c.y_min + v * (c.y_max - c.y_min)];
  }
  function draw() {
    const t0 = st.from * 60, t1 = st.to * 60;
    const keep = p => (st.team === 'all' || String(p.team) === st.team) && (st.slot === 'all' || String(p.slot) === st.slot);
    const layers = [];
    let n = 0;
    if (st.lanes) for (const lp of info.lane_paths || []) layers.push({ kind: 'paths', paths: [lp.points], color: lp.color, width: 3, alpha: 0.55 });
    if (st.heat) for (const team of [0, 1]) {
      const pts = [];
      for (const p of pos.players.filter(p => p.team === team && keep(p))) {
        for (let i = Math.floor(t0 / step); i < Math.min(p.x.length, t1 / step); i++) if (p.x[i] != null) pts.push([p.x[i], p.y[i]]);
      }
      n += pts.length;
      layers.push({ kind: 'heat', points: pts, color: team ? COLORS.t1 : COLORS.t0, radius: 12 });
    }
    const deaths = m.deaths.filter(d => d.t >= t0 && d.t <= t1 && keep({ team: d.victim_team, slot: d.victim_slot }) && d.x != null);
    if (st.deaths) layers.push({ kind: 'crosses', points: deaths.map(d => [d.x, d.y, 0, 0, d.victim_team ? COLORS.t1 : COLORS.t0]) });
    if (st.objImgs && info.objective_positions) {
      const items = [];
      for (const [k, v] of Object.entries(info.objective_positions)) {
        const src = /tier2/.test(k) ? '/img/wiki/Walker_Icon.png' : /titan|core/.test(k) ? '/img/wiki/Patrons.png' : null;
        if (!src && !/tier1/.test(k)) continue; // Guardian (tier1): sin imagen -> círculo del color del equipo
        const [x, y] = relToWorld(v.left_relative, v.top_relative);
        items.push({ x, y, src, size: 26, label: k.startsWith('team0') ? COLORS.t0 : COLORS.t1 });
      }
      layers.push({ kind: 'images', items });
    }
    if (st.koth && info.koth?.length) layers.push({ kind: 'images', items: info.koth.map(([x, y]) => ({ x, y, src: '/img/wiki/Unstable_Rift.png', size: 30, label: COLORS.neutral })) });
    if (st.objectives && info.objective_positions) {
      layers.push({ kind: 'markers', points: Object.entries(info.objective_positions).map(([k, v]) => {
        const [x, y] = relToWorld(v.left_relative, v.top_relative);
        return [x, y, k.replace(/^team\d_/, '').replace('tier1_', 'G').replace('tier2_', 'W'), k.startsWith('team0') ? COLORS.t0 : COLORS.t1];
      }) });
    }
    counts.textContent = `${n} posiciones (cada ${step} s) · ${deaths.length} muertes en el rango`;
    map.setLayers(layers, { rotate: st.rotate });
  }
  await map.ready;
  draw();
}

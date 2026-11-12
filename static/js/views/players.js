import { api, getPlayers } from '../api.js';
import { el, fmt, dataTable, store, csvDownload, spinner, scaler, meter } from '../util.js';
import { icon } from '../icons.js';
import { computeScores, DEFAULT_WEIGHTS } from '../score.js';
import { openProfile } from './profile.js';

export const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];

export async function render(root, ctx) {
  root.append(spinner());
  const [players, climb] = await Promise.all([getPlayers(true), api.get('/api/climbers?days=7').catch(() => null)]);
  root.innerHTML = '';
  let mode = store.get('playersMode', 'table');
  const f = store.get('playerFilters', { q: '', team: 'all', role: '', minMatches: 0, newDays: 0, status: '', source: 'all' });
  const weights = store.get('weights', DEFAULT_WEIGHTS);
  const roles = [...new Set(players.flatMap(p => p.roles))].sort();
  const season = ctx.status?.season_names || {};

  const input = (key, attrs) => {
    const i = el('input', { ...attrs, value: f[key] });
    i.addEventListener('input', () => { f[key] = attrs.type === 'number' ? +i.value || 0 : i.value; update(); });
    return i;
  };
  const select = (key, options) => {
    const s = el('select', {}, options.map(([v, l]) => el('option', { value: v, selected: String(f[key]) === String(v) }, l)));
    s.addEventListener('change', () => { f[key] = s.value; update(); });
    return s;
  };
  const search = input('q', { type: 'search', 'aria-label': 'Buscar jugador', placeholder: 'Buscar nombre, equipo, ID…', class: 'search' });
  const modeBtn = (m, label) => {
    const b = el('button', { type: 'button', class: 'seg' + (mode === m ? ' active' : ''), 'aria-pressed': String(mode === m), title: label,
      onclick: () => { mode = m; store.set('playersMode', m); for (const x of b.parentNode.children) { const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-pressed', String(on)); } update(); } },
      icon(m === 'table' ? 'list' : 'grid'), el('span', { class: 'btn-label' }, label));
    return b;
  };
  const more = el('details', { class: 'more-filters' },
    el('summary', {}, icon('filter'), 'Más filtros y pesos del score'),
    el('div', { class: 'row' },
      el('label', {}, 'Rol', select('role', [['', 'Cualquiera'], ...roles.map(r => [r, r])])),
      el('label', {}, 'Partidas mín. (mes)', input('minMatches', { type: 'number', min: 0, style: { width: '70px' } })),
      el('label', {}, 'Nuevos en', select('newDays', [[0, '—'], [7, '7 días'], [30, '30 días']])),
      el('label', {}, 'Estado', select('status', [['', 'Cualquiera'], ...STATUSES.map(s => [s, s])])),
      el('label', {}, 'Origen', select('source', [['all', 'Todos'], ['current', 'Temporada actual'], ['lb', 'Alguna leaderboard'], ['off', 'Fuera de leaderboard']]))));
  const filters = el('div', { class: 'panel filters' },
    el('div', { class: 'row' }, search,
      el('label', {}, 'Equipo', select('team', [['all', 'Todos'], ['free', 'Libres'], ['team', 'Con equipo']])),
      el('div', { class: 'segmented', role: 'group', 'aria-label': 'Vista' }, modeBtn('table', 'Tabla'), modeBtn('cards', 'Tarjetas'))),
    more);
  const wbox = el('div', { class: 'row' });
  for (const [k, label] of [['kda', 'KDA'], ['winrate', 'Winrate'], ['volume', 'Volumen'], ['flex', 'Flexibilidad']]) {
    const val = el('span', { class: 'mono' }, weights[k]);
    const r = el('input', { type: 'range', min: 0, max: 100, value: weights[k] });
    r.addEventListener('input', () => { weights[k] = +r.value; val.textContent = r.value; store.set('weights', weights); computeScores(players, weights); update(); });
    wbox.append(el('label', {}, label, r, val));
  }
  const reset = el('button', { onclick: () => { Object.assign(weights, DEFAULT_WEIGHTS); store.set('weights', weights); root.innerHTML = ''; render(root, ctx); } }, 'Restablecer');
  const scorePanel = el('div', { class: 'weights' },
    el('h4', {}, 'Pesos del score (0–100)'),
    el('p', { class: 'muted small' }, 'Score = mezcla ponderada de KDA y winrate (ambos suavizados hacia la media con 10 partidas ficticias y pasados a percentil), volumen de partidas (logarítmico) y flexibilidad (1 − cuota del héroe principal).'),
    wbox, reset);

  computeScores(players, weights);
  const cur = String(ctx.status?.current_leaderboard_id);
  const prevRank = p => { const v = Object.entries(p.ranks).filter(([k]) => k !== cur).map(([, r]) => r); return v.length ? Math.min(...v) : null; };
  const count = el('div', { class: 'muted small' });
  const now = Date.now() / 1000;

  let sc = {};
  const cs = (k, f) => p => sc[k]?.(f(p));
  const cols = [
    { key: 'rank', label: 'Rank', num: true, keep: true, render: p => p.rank == null ? '–' : el('span', { class: 'rank-badge' + (p.rank <= 3 ? ' top' : '') }, '#' + p.rank), title: 'Posición en la leaderboard de la temporada actual' },
    { key: 'prev', label: 'Rank ant.', num: true, title: 'Mejor posición en las leaderboards extra (temporadas anteriores)',
      sort: p => prevRank(p), render: p => { const r = prevRank(p); return r == null ? '–' : el('span', { class: 'muted' }, '#' + r); } },
    { key: 'name', label: 'Jugador', keep: true, render: p => el('span', {}, p.name, ' ', p.accounts.length > 1 ? el('span', { class: 'tag', title: 'cuentas enlazadas' }, `${p.accounts.length} cuentas`) : null) },
    { key: 'team', label: 'Equipo', render: p => p.team ? el('span', { title: p.team_source }, p.team) : el('span', { class: 'tag free' }, 'libre') },
    { key: 'role_text', label: 'Roles', wrap: true, render: p => el('span', { class: 'small' }, p.role_text || '–') },
    { key: 'matches', label: 'Partidas', num: true, sort: p => p.stats.matches, render: p => fmt.int(p.stats.matches) },
    { key: 'winrate', label: 'WR', num: true, sort: p => p.stats.winrate, cellClass: cs('wr', p => p.stats.winrate), render: p => fmt.pct(p.stats.winrate) },
    { key: 'kd', label: 'KD', num: true, sort: p => p.stats.kd, cellClass: cs('kd', p => p.stats.kd), render: p => fmt.dec(p.stats.kd) },
    { key: 'kda', label: 'KDA', num: true, sort: p => p.stats.kda, cellClass: cs('kda', p => p.stats.kda), render: p => fmt.dec(p.stats.kda) },
    { key: 'dmg', label: 'Daño/partida', num: true, sort: p => p.stats.damage_per_match, cellClass: cs('dmg', p => p.stats.damage_per_match), render: p => fmt.int(p.stats.damage_per_match) },
    { key: 'obj', label: 'Daño obj./min', num: true, sort: p => p.stats.obj_damage_per_min, cellClass: cs('obj', p => p.stats.obj_damage_per_min), render: p => fmt.int(p.stats.obj_damage_per_min) },
    { key: 'reliability', label: 'Fiabilidad', sort: p => p.stats.matches, render: p => el('span', { class: 'tag ' + p.reliability.toLowerCase() }, p.reliability), title: 'Alta ≥25 partidas del mes, Media 10–24, Baja <10' },
    { key: 'score', label: 'Score', num: true, render: scoreBar },
    { key: 'status', label: 'Estado', keep: true, sort: p => p.manual.status, render: p => el('span', { class: 'status-pill s-' + p.manual.status.replace(/\s+/g, '-') }, p.manual.status) },
  ];
  const table = dataTable(cols, [], { sortKey: 'score', asc: false, hideEmpty: true, label: 'Jugadores', onRowClick: p => openProfile(p.id, ctx),
    emptyText: players.length ? 'Sin resultados con estos filtros.' : 'Todavía no hay jugadores. La primera actualización se lanza sola al arrancar; mira el progreso arriba.' });
  const exportBtn = el('button', { onclick: () => csvDownload('jugadores.csv', [
    { key: 'rank', label: 'rank' }, { key: 'name', label: 'nombre' }, { label: 'account_id', csv: p => p.primary_account_id },
    { label: 'equipo', csv: p => p.team || '' }, { label: 'roles', csv: p => p.role_text }, { label: 'partidas', csv: p => p.stats.matches },
    { label: 'winrate', csv: p => p.stats.winrate?.toFixed(3) }, { label: 'kda', csv: p => p.stats.kda?.toFixed(2) },
    { label: 'score', csv: p => p.score?.toFixed(1) }, { label: 'estado', csv: p => p.manual.status }], filtered()) }, 'Exportar CSV');

  function filtered() {
    const q = f.q.trim().toLowerCase();
    return players.filter(p => {
      if (q && !(p.name.toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q) || p.accounts.some(a => String(a.account_id).includes(q)))) return false;
      if (f.team === 'free' && p.team) return false;
      if (f.team === 'team' && !p.team) return false;
      if (f.role && !p.roles.includes(f.role)) return false;
      if (f.minMatches && p.stats.matches < f.minMatches) return false;
      if (f.status && p.manual.status !== f.status) return false;
      if (f.source === 'current' && p.rank == null) return false;
      if (f.source === 'lb' && !Object.keys(p.ranks).length) return false;
      if (f.source === 'off' && Object.keys(p.ranks).length) return false;
      if (+f.newDays) {
        // nuevo = apareció en la leaderboard actual en los últimos N días y DESPUÉS del primer snapshot
        if (!p.first_in_current || p.first_in_current <= p.history_start) return false;
        if (p.first_in_current < now - f.newDays * 86400) return false;
      }
      return true;
    });
  }
  const highlights = el('div', { class: 'highlights' });
  const cards = el('div', { class: 'pcards' });
  const hiddenNote = el('span', { class: 'muted small' });
  function update() {
    store.set('playerFilters', f);
    const rows = filtered();
    sc = {
      wr: scaler(rows.filter(p => p.stats.matches >= 10).map(p => p.stats.winrate)),
      kd: scaler(rows.map(p => p.stats.kd)), kda: scaler(rows.map(p => p.stats.kda)),
      dmg: scaler(rows.map(p => p.stats.damage_per_match)), obj: scaler(rows.map(p => p.stats.obj_damage_per_min)),
    };
    table.hidden = mode !== 'table'; cards.hidden = mode !== 'cards';
    if (mode === 'table') table.update(rows); else renderCards(rows);
    hiddenNote.textContent = mode === 'table' && table.hiddenColumns ? `${table.hiddenColumns} columnas sin datos ocultas` : '';
    const lbs = Object.entries(season).map(([k, v]) => `${v} (${k})`).join(' · ');
    count.textContent = `${rows.length} de ${players.length} jugadores · ${ctx.status?.region || ''} · leaderboards: ${lbs || '—'}`;
  }
  function renderCards(rows) {
    cards.innerHTML = '';
    const sorted = rows.slice().sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || (a.rank ?? 1e9) - (b.rank ?? 1e9));
    if (!sorted.length) cards.append(el('div', { class: 'empty' }, 'Sin resultados con estos filtros.'));
    for (const p of sorted.slice(0, 120)) cards.append(playerCard(p, ctx));
    if (sorted.length > 120) cards.append(el('div', { class: 'muted small' }, `Mostrando 120 de ${sorted.length}; usa los filtros o la vista de tabla.`));
  }
  renderHighlights(highlights, players, climb, ctx);
  more.querySelector('.row').after(scorePanel);
  root.append(highlights, filters, el('div', { class: 'panel' }, el('div', { class: 'row table-head' }, count, hiddenNote, el('span', { class: 'spacer' }), exportBtn), table, cards));
  update();
}

function scoreBar(p) {
  if (p.score == null) return el('span', { class: 'muted' }, '–');
  const v = Math.round(p.score);
  return meter(v, 100, { cls: v >= 70 ? 'hi' : v >= 40 ? 'mid' : 'lo', label: `Score ${v} de 100` });
}

function playerCard(p, ctx) {
  const s = p.stats;
  return el('button', { type: 'button', class: 'pcard', onclick: () => openProfile(p.id, ctx), 'aria-label': `Abrir perfil de ${p.name}` },
    el('div', { class: 'pcard-top' },
      el('span', { class: 'rank-badge' + (p.rank && p.rank <= 3 ? ' top' : '') }, p.rank ? '#' + p.rank : '—'),
      el('span', { class: 'pcard-name' }, p.name),
      p.team ? el('span', { class: 'tag' }, p.team) : el('span', { class: 'tag free' }, 'libre')),
    el('div', { class: 'pcard-score' }, el('span', { class: 'lbl' }, 'Score'), scoreBar(p)),
    el('div', { class: 'pcard-stats' },
      el('div', {}, el('b', {}, fmt.int(s.matches)), el('span', {}, 'partidas')),
      el('div', {}, el('b', {}, fmt.pct(s.winrate)), el('span', {}, 'winrate')),
      el('div', {}, el('b', {}, fmt.dec(s.kda)), el('span', {}, 'KDA'))),
    el('div', { class: 'pcard-roles small muted' }, p.role_text || 'Roles sin datos'));
}

function renderHighlights(box, players, climb, ctx) {
  const item = (ic, title, p, value, sub) => el('button', { type: 'button', class: 'hl', disabled: !p, onclick: () => p && openProfile(p.id, ctx) },
    el('span', { class: 'hl-ico' }, icon(ic)),
    el('span', { class: 'hl-body' }, el('span', { class: 'hl-title' }, title),
      el('span', { class: 'hl-name' }, p ? p.name : 'Sin datos aún'),
      el('span', { class: 'hl-sub' }, sub)),
    el('span', { class: 'hl-val' }, value));
  const scored = players.filter(p => p.score != null).sort((a, b) => b.score - a.score);
  const top = scored.length ? scored.slice(0, 3) : players.filter(p => p.rank != null).sort((a, b) => a.rank - b.rank).slice(0, 3);
  const byScore = scored.length > 0;
  top.forEach((p, i) => box.append(item(i ? 'star' : 'trophy', byScore ? `Top ${i + 1} por score` : `Top ${i + 1} leaderboard`, p,
    byScore ? Math.round(p.score) : '#' + p.rank, p.team || 'libre')));
  const wr = players.filter(p => p.stats.matches >= 10 && p.stats.winrate != null).sort((a, b) => b.stats.winrate - a.stats.winrate)[0];
  box.append(item('sword', 'Mejor winrate (≥10 partidas)', wr, wr ? fmt.pct(wr.stats.winrate) : '–', wr ? `${wr.stats.matches} partidas` : 'faltan stats del mes'));
  const c = climb?.climbers?.slice().sort((a, b) => b.delta - a.delta)[0];
  const cp = c && players.find(p => p.id === c.player_id);
  box.append(item('climbers', 'Mayor subida (7 días)', cp, c ? '+' + c.delta : '–', c ? `#${c.from} → #${c.to}` : 'hace falta más historial'));
}

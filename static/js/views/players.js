import { getPlayers } from '../api.js';
import { el, fmt, dataTable, store, csvDownload, spinner } from '../util.js';
import { computeScores, DEFAULT_WEIGHTS } from '../score.js';
import { openProfile } from './profile.js';

export const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];

export async function render(root, ctx) {
  root.append(spinner());
  const players = await getPlayers(true);
  root.innerHTML = '';
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
  const filters = el('div', { class: 'panel row' },
    input('q', { type: 'search', placeholder: 'Buscar nombre, equipo, ID…', style: { minWidth: '220px' } }),
    el('label', {}, 'Equipo', select('team', [['all', 'Todos'], ['free', 'Libres'], ['team', 'Con equipo']])),
    el('label', {}, 'Rol', select('role', [['', 'Cualquiera'], ...roles.map(r => [r, r])])),
    el('label', {}, 'Partidas mín. (mes)', input('minMatches', { type: 'number', min: 0, style: { width: '70px' } })),
    el('label', {}, 'Nuevos en', select('newDays', [[0, '—'], [7, '7 días'], [30, '30 días']])),
    el('label', {}, 'Estado', select('status', [['', 'Cualquiera'], ...STATUSES.map(s => [s, s])])),
    el('label', {}, 'Origen', select('source', [['all', 'Todos'], ['current', 'Temporada actual'], ['lb', 'Alguna leaderboard'], ['off', 'Fuera de leaderboard']])),
  );

  const wbox = el('div', { class: 'row' });
  for (const [k, label] of [['kda', 'KDA'], ['winrate', 'Winrate'], ['volume', 'Volumen'], ['flex', 'Flexibilidad']]) {
    const val = el('span', { class: 'mono' }, weights[k]);
    const r = el('input', { type: 'range', min: 0, max: 100, value: weights[k] });
    r.addEventListener('input', () => { weights[k] = +r.value; val.textContent = r.value; store.set('weights', weights); computeScores(players, weights); update(); });
    wbox.append(el('label', {}, label, r, val));
  }
  const reset = el('button', { onclick: () => { Object.assign(weights, DEFAULT_WEIGHTS); store.set('weights', weights); root.innerHTML = ''; render(root, ctx); } }, 'Restablecer');
  const scorePanel = el('details', { class: 'panel' },
    el('summary', {}, 'Pesos del score (0–100)'),
    el('p', { class: 'muted small' }, 'Score = mezcla ponderada de KDA y winrate (ambos suavizados hacia la media con 10 partidas ficticias y pasados a percentil), volumen de partidas (logarítmico) y flexibilidad (1 − cuota del héroe principal).'),
    wbox, reset);

  computeScores(players, weights);
  const cur = String(ctx.status?.current_leaderboard_id);
  const prevRank = p => { const v = Object.entries(p.ranks).filter(([k]) => k !== cur).map(([, r]) => r); return v.length ? Math.min(...v) : null; };
  const count = el('div', { class: 'muted small' });
  const now = Date.now() / 1000;

  const cols = [
    { key: 'rank', label: 'Rank', num: true, render: p => p.rank ?? '–', title: 'Posición en la leaderboard de la temporada actual' },
    { key: 'prev', label: 'Rank ant.', num: true, title: 'Mejor posición en las leaderboards extra (temporadas anteriores)',
      sort: p => prevRank(p), render: p => { const r = prevRank(p); return r == null ? '–' : el('span', { class: 'muted' }, '#' + r); } },
    { key: 'name', label: 'Jugador', render: p => el('span', {}, p.name, ' ', p.accounts.length > 1 ? el('span', { class: 'tag', title: 'cuentas enlazadas' }, `${p.accounts.length} cuentas`) : null) },
    { key: 'team', label: 'Equipo', render: p => p.team ? el('span', { title: p.team_source }, p.team) : el('span', { class: 'tag free' }, 'libre') },
    { key: 'role_text', label: 'Roles', wrap: true, render: p => el('span', { class: 'small' }, p.role_text || '–') },
    { key: 'matches', label: 'Partidas', num: true, sort: p => p.stats.matches, render: p => fmt.int(p.stats.matches) },
    { key: 'winrate', label: 'WR', num: true, sort: p => p.stats.winrate, render: p => fmt.pct(p.stats.winrate) },
    { key: 'kd', label: 'KD', num: true, sort: p => p.stats.kd, render: p => fmt.dec(p.stats.kd) },
    { key: 'kda', label: 'KDA', num: true, sort: p => p.stats.kda, render: p => fmt.dec(p.stats.kda) },
    { key: 'dmg', label: 'Daño/partida', num: true, sort: p => p.stats.damage_per_match, render: p => fmt.int(p.stats.damage_per_match) },
    { key: 'obj', label: 'Daño obj./min', num: true, sort: p => p.stats.obj_damage_per_min, render: p => fmt.int(p.stats.obj_damage_per_min) },
    { key: 'reliability', label: 'Fiabilidad', sort: p => p.stats.matches, render: p => el('span', { class: 'tag ' + p.reliability.toLowerCase() }, p.reliability), title: 'Alta ≥25 partidas del mes, Media 10–24, Baja <10' },
    { key: 'score', label: 'Score', num: true, render: p => el('span', { class: 'score' }, p.score == null ? '–' : Math.round(p.score)) },
    { key: 'status', label: 'Estado', sort: p => p.manual.status, render: p => p.manual.status === 'pendiente' ? el('span', { class: 'muted' }, 'pendiente') : p.manual.status },
  ];
  const table = dataTable(cols, [], { sortKey: 'score', asc: false, onRowClick: p => openProfile(p.id, ctx) });
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
  function update() {
    store.set('playerFilters', f);
    const rows = filtered();
    table.update(rows);
    const lbs = Object.entries(season).map(([k, v]) => `${v} (${k})`).join(' · ');
    count.textContent = `${rows.length} de ${players.length} jugadores · ${ctx.status?.region || ''} · leaderboards: ${lbs || '—'}`;
  }
  root.append(filters, scorePanel, el('div', { class: 'panel' }, el('div', { class: 'row', style: { justifyContent: 'space-between' } }, count, exportBtn), table));
  if (!players.length) root.append(el('div', { class: 'empty' }, 'Todavía no hay jugadores. La primera actualización se lanza sola al arrancar; mira el progreso arriba a la derecha.'));
  update();
}

import { api, getPlayers, invalidatePlayers } from '../api.js';
import { el, fmt, dataTable, toast, spinner } from '../util.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  root.append(spinner());
  const [teams, players] = await Promise.all([api.get('/api/teams'), getPlayers()]);
  root.innerHTML = '';
  const byId = Object.fromEntries(players.map(p => [p.id, p]));
  const free = players.filter(p => !p.team);
  const addInput = el('input', { 'aria-label': 'Cuenta del jugador a añadir', placeholder: 'ID / [U:1:N] / steam64 / URL', style: { minWidth: '240px' } });
  root.append(el('div', { class: 'panel row' },
    el('button', { onclick: async () => {
      try { const r = await api.post('/api/teams/reload'); invalidatePlayers(); toast(`equipos.txt: ${r.lines} líneas` + (r.errors.length ? ` · ${r.errors.length} errores (ver terminal)` : '')); root.innerHTML = ''; render(root, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Recargar equipos.txt'),
    el('span', { class: 'muted small' }, `${teams.length} equipos · ${players.length - free.length} jugadores con equipo · ${free.length} libres`),
    el('span', { style: { marginLeft: 'auto' } }), addInput,
    el('button', { onclick: async () => {
      try { const r = await api.post('/api/players/add', { account: addInput.value }); invalidatePlayers(); openProfile(r.player_id, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Añadir jugador por ID')));
  if (!teams.length) root.append(el('div', { class: 'empty' }, 'No hay equipos. Edita equipos.txt (una línea por jugador: IDs y nombre del equipo) y pulsa «Recargar».'));
  const grid = el('div', { class: 'grid2' });
  for (const t of teams) {
    const rows = t.players.map(x => byId[x.id]).filter(Boolean);
    const m = rows.reduce((a, p) => a + p.stats.matches, 0);
    grid.append(el('div', { class: 'panel' },
      el('div', { class: 'row', style: { justifyContent: 'space-between' } }, el('h3', {}, t.team),
        el('a', { href: `#informe?team=${encodeURIComponent(t.team)}` }, 'Informe →')),
      el('div', { class: 'muted small' }, `${rows.length} jugadores · ${t.accounts.length} cuentas en la plantilla · ${fmt.int(m)} partidas en 30 días`),
      dataTable([
        { key: 'name', label: 'Jugador' }, { key: 'rank', label: 'Rank', num: true, render: p => p.rank ?? '–' },
        { key: 'role_text', label: 'Roles', wrap: true, render: p => el('span', { class: 'small' }, p.role_text || '–') },
        { key: 'm', label: 'Partidas', num: true, sort: p => p.stats.matches, render: p => p.stats.matches },
        { key: 'kda', label: 'KDA', num: true, sort: p => p.stats.kda, render: p => fmt.dec(p.stats.kda) },
        { key: 'src', label: 'Origen', render: p => p.team_source },
      ], rows, { sortKey: 'm', onRowClick: p => openProfile(p.id, ctx) })));
  }
  root.append(grid);
}

import { api, getPlayers, invalidatePlayers } from '../api.js';
import { el, fmt, dataTable, toast, spinner } from '../util.js';
import { openProfile } from './profile.js';
import { scoreRing, rankEmblem, roleChips, roleColor, statTile, getRanks } from '../ui.js';
import { computeScores, loadWeights } from '../score.js';

export async function render(root, ctx) {
  const [teams, players] = await Promise.all([api.get('/api/teams'), getPlayers()]);
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
  const ranks = await getRanks();
  const weights = loadWeights();
  computeScores(players, weights);
  const ROLES = ['Carry', 'Off-carry', 'Initiator', 'Frontline', 'Catcher', 'Support'];
  const grid = el('div', { class: 'team-cards' });
  for (const t of teams) {
    const rows = t.players.map(x => byId[x.id]).filter(Boolean);
    const scored = rows.filter(p => p.score != null);
    const avg = scored.length ? scored.reduce((a, p) => a + p.score, 0) / scored.length : null;
    const bs = rows.filter(p => p.badge);
    const avgBadge = bs.length ? Math.round(bs.reduce((a, p) => a + p.badge, 0) / bs.length) : null;
    const covered = new Set(rows.flatMap(p => [p.role_primary, p.role_secondary].filter(Boolean)));
    const roster = el('details', {}, el('summary', { class: 'muted small' }, 'Ver plantilla'),
      dataTable([
        { key: 'name', label: 'Jugador' }, { key: 'rank', label: 'Rank', num: true, render: p => p.rank ? '#' + p.rank : '–' },
        { key: 'role', label: 'Rol', sortable: false, render: p => roleChips(p) },
        { key: 'm', label: 'Partidas', num: true, sort: p => p.stats.matches, render: p => p.stats.matches },
        { key: 'score', label: 'Score', num: true, sort: p => p.score, render: p => scoreRing(p.score, { lo: p._lo, hi: p._hi, size: 40 }) },
      ], rows, { sortKey: 'score', onRowClick: p => openProfile(p.id, ctx) }));
    grid.append(el('div', { class: 'panel team-card3' },
      el('h3', {}, t.team),
      el('div', { class: 'roster-avs' }, rows.map(p => el('button', { type: 'button', class: 'linkbtn', title: p.name, 'aria-label': `Perfil de ${p.name}`, onclick: () => openProfile(p.id, ctx) },
        p.avatar ? el('img', { class: 'avatar-img', src: p.avatar, alt: '' }) : el('span', { class: 'avatar-img', style: { display: 'inline-grid', placeItems: 'center' } }, p.name[0])))),
      el('div', { class: 'pf-tiles', style: { margin: 0 } },
        statTile('Score medio', avg == null ? '–' : Math.round(avg)),
        statTile('Rango medio', avgBadge ? rankEmblem(avgBadge, ranks) : '–'),
        statTile('Roles', el('span', { class: 'role-dots', role: 'img', 'aria-label': 'Roles cubiertos: ' + ([...covered].join(', ') || 'ninguno') },
          ROLES.map(r => el('i', { class: covered.has(r) ? 'on' : '', style: { '--role': roleColor(r) }, title: r }))), { sub: `${covered.size}/6 cubiertos` })),
      el('div', { class: 'muted small' }, `${rows.length} jugadores · ${t.accounts.length} cuentas · ${fmt.int(rows.reduce((a, p) => a + p.stats.matches, 0))} partidas en el periodo`),
      el('div', { class: 'row' }, el('a', { class: 'btn', href: `#informe?team=${encodeURIComponent(t.team)}` }, 'Ver informe'),
        el('a', { class: 'btn', href: `#informe?team=${encodeURIComponent(t.team)}` }, 'Partidas recientes')),
      roster));
  }
  root.append(grid);
}

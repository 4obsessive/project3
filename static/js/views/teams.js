import { api, getPlayers, getHeroes, invalidatePlayers } from '../api.js';
import { el, fmt, dataTable, toast, spinner } from '../util.js';
import { openProfile } from './profile.js';
import { scoreRing, rankEmblem, roleChips, roleColor, statTile, getRanks, playerPic, cellBar, heroArt } from '../ui.js';
import { computeScores, loadWeights } from '../score.js';

export async function render(root, ctx) {
  const [teams, players, heroList] = await Promise.all([api.get('/api/teams'), getPlayers(), getHeroes().catch(() => [])]);
  const heroById = new Map(heroList.map(h => [h.id, h]));
  const heroOf = p => p.heroes?.[0] && (heroById.get(p.heroes[0].hero_id) || { name: p.heroes[0].name });
  const byId = Object.fromEntries(players.map(p => [p.id, p]));
  const free = players.filter(p => !p.team);
  const addInput = el('input', { 'aria-label': 'Account of the player to add', placeholder: 'ID / [U:1:N] / steam64 / URL', style: { minWidth: '240px' } });
  root.append(el('div', { class: 'panel row' },
    el('button', { onclick: async () => {
      try { const r = await api.post('/api/teams/reload'); invalidatePlayers(); toast(`equipos.txt: ${r.lines} lines` + (r.errors.length ? ` · ${r.errors.length} errors (see terminal)` : '')); root.innerHTML = ''; render(root, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Reload equipos.txt'),
    el('span', { class: 'muted small' }, `${teams.length} teams · ${players.length - free.length} players with a team · ${free.length} free agents`),
    el('span', { style: { marginLeft: 'auto' } }), addInput,
    el('button', { onclick: async () => {
      try { const r = await api.post('/api/players/add', { account: addInput.value }); invalidatePlayers(); openProfile(r.player_id, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Add player by ID')));
  if (!teams.length) root.append(el('div', { class: 'empty' }, 'No teams. Edit equipos.txt (one line per player: IDs and team name) and press "Reload".'));
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
    const maxMatches = Math.max(1, ...rows.map(p => p.stats.matches || 0));
    const roster = el('details', {}, el('summary', { class: 'muted small' }, 'View roster'),
      dataTable([
        { key: 'name', label: 'Player', render: p => el('span', { class: 'pl-cell' }, playerPic(p, heroOf(p), { size: 'mini' }), el('span', { class: 'nm' }, p.name)) }, { key: 'rank', label: 'Rank', num: true, render: p => p.rank ? '#' + p.rank : '–' },
        { key: 'role', label: 'Role', sortable: false, render: p => roleChips(p) },
        { key: 'm', label: 'Matches', num: true, sort: p => p.stats.matches, render: p => cellBar(p.stats.matches, maxMatches, fmt.int(p.stats.matches)) },
        { key: 'score', label: 'Score', num: true, sort: p => p.score, render: p => scoreRing(p.score, { lo: p._lo, hi: p._hi, size: 40 }) },
      ], rows, { sortKey: 'score', onRowClick: p => openProfile(p.id, ctx) }));
    grid.append(el('div', { class: 'panel team-card3' },
      el('h3', {}, t.team),
      el('div', { class: 'roster-avs' }, rows.map(p => el('button', { type: 'button', class: 'linkbtn', title: p.name, 'aria-label': `Profile of ${p.name}`, onclick: () => openProfile(p.id, ctx) },
        p.avatar ? el('img', { class: 'avatar-img', src: p.avatar, alt: '' }) : el('span', { class: 'avatar-img', style: { display: 'inline-grid', placeItems: 'center' } }, p.name[0])))),
      el('div', { class: 'pf-tiles', style: { margin: 0 } },
        statTile('Average score', avg == null ? '–' : Math.round(avg)),
        statTile('Average rank', avgBadge ? rankEmblem(avgBadge, ranks) : '–'),
        statTile('Roles', el('span', { class: 'role-dots', role: 'img', 'aria-label': 'Roles covered: ' + ([...covered].join(', ') || 'none') },
          ROLES.map(r => el('i', { class: covered.has(r) ? 'on' : '', style: { '--role': roleColor(r) }, title: r }))), { sub: `${covered.size}/6 covered` })),
      el('div', { class: 'muted small' }, `${rows.length} players · ${t.accounts.length} accounts · ${fmt.int(rows.reduce((a, p) => a + p.stats.matches, 0))} matches in the period`),
      el('div', { class: 'row' }, el('a', { class: 'btn', href: `#report?team=${encodeURIComponent(t.team)}` }, 'View report'),
        el('a', { class: 'btn', href: `#report?team=${encodeURIComponent(t.team)}` }, 'Recent matches')),
      roster));
  }
  root.append(grid);
}

import { api, getPlayers } from '../api.js';
import { el, fmt, dataTable, store, spinner } from '../util.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  let days = store.get('climbDays', 7);
  const sel = el('select', {}, [7, 14, 30].map(d => el('option', { value: d, selected: d === days }, `${d} días`)));
  const body = el('div');
  root.append(el('div', { class: 'panel row' }, el('label', {}, 'Comparar con hace', sel),
    el('span', { class: 'muted small' }, 'La API no da el ranking pasado: el historial se acumula desde la primera descarga (un snapshot por actualización).')), body);
  sel.addEventListener('change', () => { days = +sel.value; store.set('climbDays', days); load(); });

  async function load() {
    body.innerHTML = ''; body.append(spinner());
    const [c, players] = await Promise.all([api.get(`/api/climbers?days=${days}`), getPlayers()]);
    const byId = Object.fromEntries(players.map(p => [p.id, p]));
    body.innerHTML = '';
    if (c.warning) body.append(el('div', { class: 'note warning block' }, c.warning));
    if (c.snapshots < 2) return;
    body.append(el('div', { class: 'muted small' }, `Comparando ${fmt.datetime(c.base_taken_at)} → ${fmt.datetime(c.latest_taken_at)} (${c.snapshots} snapshots)`));
    const extra = r => byId[r.player_id] || {};
    body.append(el('div', { class: 'grid2' },
      el('div', { class: 'panel' }, el('h3', {}, `Los que más suben (${c.climbers.length})`), dataTable([
        { key: 'name', label: 'Jugador' },
        { key: 'team', label: 'Equipo', render: r => extra(r).team || el('span', { class: 'tag free' }, 'libre') },
        { key: 'from', label: 'Antes', num: true, render: r => '#' + r.from }, { key: 'to', label: 'Ahora', num: true, render: r => '#' + r.to },
        { key: 'delta', label: 'Sube', num: true, render: r => el('b', { style: { color: 'var(--ok)' } }, '+' + r.delta) },
        { key: 'roles', label: 'Roles', sortable: false, render: r => el('span', { class: 'small' }, extra(r).role_text || '–') },
      ], c.climbers, { sortKey: 'delta', onRowClick: r => openProfile(r.player_id, ctx) })),
      el('div', { class: 'panel' }, el('h3', {}, `Nuevos en el ranking (${c.new.length})`), dataTable([
        { key: 'name', label: 'Jugador' }, { key: 'rank', label: 'Rank', num: true, render: r => '#' + r.rank },
        { key: 'team', label: 'Equipo', render: r => extra(r).team || el('span', { class: 'tag free' }, 'libre') },
        { key: 'roles', label: 'Roles', sortable: false, render: r => el('span', { class: 'small' }, extra(r).role_text || '–') },
      ], c.new, { sortKey: 'rank', asc: true, onRowClick: r => openProfile(r.player_id, ctx) }))));
  }
  load();
}

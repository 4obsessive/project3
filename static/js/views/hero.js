// Por héroe: mejores jugadores con un héroe. Mínimo 30 jugadores: se empieza exigiendo 15 partidas
// con el héroe y se baja el mínimo solo si hace falta, avisando.
import { getPlayers, getHeroes } from '../api.js';
import { el, fmt, dataTable, store, spinner } from '../util.js';
import { openProfile } from './profile.js';

const TARGET = 30, START_MIN = 15;

export async function render(root, ctx) {
  root.append(spinner());
  const [players, heroes] = await Promise.all([getPlayers(), getHeroes()]);
  root.innerHTML = '';
  let heroId = store.get('hero', heroes[0]?.id);
  let freeOnly = store.get('heroFreeOnly', false);
  const sel = el('select', {}, heroes.map(h => el('option', { value: h.id, selected: h.id === heroId }, h.name)));
  const free = el('input', { type: 'checkbox', checked: freeOnly });
  const info = el('div', { class: 'note info' });
  const tableBox = el('div');
  root.append(el('div', { class: 'panel row' }, el('label', {}, 'Héroe', sel), el('label', {}, free, 'solo libres')), el('div', { class: 'panel' }, info, tableBox));
  sel.addEventListener('change', () => { heroId = +sel.value; store.set('hero', heroId); update(); });
  free.addEventListener('change', () => { freeOnly = free.checked; store.set('heroFreeOnly', freeOnly); update(); });

  function update() {
    const rows = [];
    for (const p of players) {
      if (freeOnly && p.team) continue;
      const h = p.heroes.find(h => h.hero_id === heroId);
      if (h) rows.push({ ...h, player: p, pname: p.name, team: p.team });
    }
    let min = START_MIN;
    while (min > 1 && rows.filter(r => r.matches >= min).length < TARGET) min--;
    const shown = rows.filter(r => r.matches >= min);
    const hn = heroes.find(h => h.id === heroId)?.name;
    info.className = 'note ' + (min < START_MIN ? 'warning' : 'info');
    info.textContent = min < START_MIN
      ? `Mínimo bajado de ${START_MIN} a ${min} partidas con ${hn} para llegar a ${TARGET} jugadores (${shown.length} mostrados). Con pocas partidas el KDA es poco fiable.`
      : `${shown.length} jugadores con al menos ${START_MIN} partidas de ${hn} en los últimos 30 días.`;
    tableBox.innerHTML = '';
    tableBox.append(dataTable([
      { key: 'pname', label: 'Jugador' },
      { key: 'team', label: 'Equipo', render: r => r.team || el('span', { class: 'tag free' }, 'libre') },
      { key: 'matches', label: 'Partidas', num: true },
      { key: 'share', label: '% de sus partidas', num: true, sort: r => r.matches / r.player.stats.matches, render: r => fmt.pct(r.matches / r.player.stats.matches) },
      { key: 'winrate', label: 'WR', fmt: 'pct' }, { key: 'kd', label: 'KD', fmt: '2' }, { key: 'kda', label: 'KDA', fmt: '2' },
      { key: 'damage_per_match', label: 'Daño/partida', fmt: 'int' },
      { key: 'rank', label: 'Rank', num: true, sort: r => r.player.rank, render: r => r.player.rank ?? '–' },
    ], shown, { sortKey: 'kda', onRowClick: r => openProfile(r.player.id, ctx) }));
  }
  update();
}

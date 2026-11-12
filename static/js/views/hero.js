// Por héroe: ranking de jugadores seguidos con un héroe, por winrate ajustado e índice de KDA.
// Nunca se baja de 5 partidas: si hay pocos jugadores se muestran menos y se dice.
import { getPlayers, getHeroes } from '../api.js';
import { el, fmt, dataTable, store } from '../util.js';
import { heroArt, wrBar, confidencePips, sectionHead, emptyState } from '../ui.js';
import { openProfile } from './profile.js';

const FLOOR = 5;

export async function render(root, ctx) {
  const [players, heroes] = await Promise.all([getPlayers(), getHeroes()]);
  let heroId = +ctx.params[0] || store.get('hero', heroes[0]?.id);
  let freeOnly = store.get('heroFreeOnly', false);
  let minM = Math.max(FLOOR, store.get('heroMin', 10));
  const pooled = new Map();
  for (const p of players) for (const h of p.heroes) {
    const x = pooled.get(h.hero_id) || { m: 0, w: 0, n: 0 };
    x.m += h.matches; x.w += h.wins; x.n += 1; pooled.set(h.hero_id, x);
  }
  const q = el('input', { type: 'search', class: 'search', 'aria-label': 'Buscar héroe', placeholder: 'Buscar héroe…', style: { width: '100%', marginBottom: '10px' } });
  const grid = el('div', { class: 'hero-pick', role: 'group', 'aria-label': 'Héroes' });
  const btns = new Map();
  for (const h of heroes) {
    const b = el('button', { type: 'button', 'aria-pressed': String(h.id === heroId), title: h.name, 'aria-label': h.name, onclick: () => choose(h.id) },
      heroArt(h, { size: 'card', label: true }));
    btns.set(h.id, b); grid.append(b);
  }
  q.addEventListener('input', () => { const t = q.value.trim().toLowerCase(); for (const h of heroes) btns.get(h.id).hidden = !!t && !h.name.toLowerCase().includes(t); });
  const free = el('input', { type: 'checkbox', checked: freeOnly });
  free.addEventListener('change', () => { freeOnly = free.checked; store.set('heroFreeOnly', freeOnly); update(); });
  const slider = el('input', { type: 'range', min: FLOOR, max: 50, value: minM, 'aria-label': 'Partidas mínimas con el héroe' });
  const sv = el('span', { class: 'mono' }, minM);
  slider.addEventListener('input', () => { minM = +slider.value; sv.textContent = minM; store.set('heroMin', minM); update(); });
  const right = el('div');
  root.append(el('div', { class: 'split' }, el('div', { class: 'panel' }, q, grid), right));

  function choose(id) {
    heroId = id; store.set('hero', id);
    for (const [hid, b] of btns) b.setAttribute('aria-pressed', String(hid === id));
    update();
  }
  function update() {
    const hero = heroes.find(h => h.id === heroId) || {};
    const pool = pooled.get(heroId) || { m: 0, w: 0, n: 0 };
    const rows = [];
    for (const p of players) {
      if (freeOnly && p.team) continue;
      const h = p.heroes.find(h => h.hero_id === heroId);
      if (h && h.matches >= minM) rows.push({ ...h, player: p, pname: p.name, share: h.matches / p.stats.matches });
    }
    right.innerHTML = '';
    right.append(el('div', { class: 'hero-banner3' }, heroArt(hero, { size: 'card', kind: 'bg' }),
      el('div', {}, el('h2', {}, hero.name || '—'),
        el('div', { class: 'hb-stats' },
          el('span', {}, el('b', {}, pool.m ? fmt.pct(pool.w / pool.m) : '–'), 'WR conjunto'),
          el('span', {}, el('b', {}, fmt.int(pool.m)), 'partidas'),
          el('span', {}, el('b', {}, pool.n), 'jugadores')))));
    right.append(sectionHead('Ranking', el('label', { class: 'small muted row' }, 'Mín. partidas', slider, sv), el('label', { class: 'small muted row' }, free, 'solo libres')));
    if (!rows.length) { right.append(emptyState(`Ningún jugador seguido tiene ${minM}+ partidas con ${hero.name} en el periodo.`)); return; }
    if (rows.length < 10) right.append(el('p', { class: 'note info' }, `Solo ${rows.length} jugadores con ${minM}+ partidas: no se baja el mínimo de ${FLOOR} para no premiar muestras minúsculas.`));
    right.append(dataTable([
      { key: 'pname', label: 'Jugador', render: r => el('span', {}, r.pname, r.player.team ? '' : el('span', { class: 'small', style: { color: 'var(--spirit)', marginLeft: '6px' } }, 'libre')) },
      { key: 'matches', label: 'Partidas', num: true },
      { key: 'share', label: '% de sus partidas', num: true, fmt: 'pct' },
      { key: 'wr_adj', label: 'WR', num: true, render: r => wrBar(r.winrate, { lo: r.wr_lo, hi: r.wr_hi, muted: r.matches < 20, n: r.matches }) },
      { key: 'idx_kda', label: 'KDA idx', num: true, fmt: '2' },
      { key: 'dmg_per_min', label: 'Daño/min', num: true, fmt: 'int' },
      { key: 'conf', label: 'Confianza', sort: r => r.matches, render: r => confidencePips(r.reliability, { wr: r.winrate, n: r.matches, lo: r.wr_lo, hi: r.wr_hi }) },
    ], rows, { sortKey: 'wr_adj', label: `Jugadores de ${hero.name}`, onRowClick: r => openProfile(r.player.id, ctx) }));
  }
  update();
}

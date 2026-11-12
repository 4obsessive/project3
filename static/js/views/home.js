// Inicio: qué es la herramienta, KPIs, climbers de la semana, últimas partidas y accesos rápidos.
import { api, getPlayers, getHeroes } from '../api.js';
import { el, fmt } from '../util.js';
import { heroArt, scoreRing, deltaChip, sectionHead, emptyState, windowText } from '../ui.js';
import { computeScores, loadWeights } from '../score.js';
import { heroPortrait } from '../art.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  const [status, players, matches, climb, heroList] = await Promise.all([
    api.get('/api/status').catch(() => ctx.status),
    getPlayers().catch(() => []),
    api.get('/api/matches').catch(() => []),
    api.get('/api/climbers?days=7').catch(() => null),
    getHeroes().catch(() => []),
  ]);
  const counts = status?.counts || {};
  const heroById = new Map(heroList.map(h => [h.id, h]));
  const heroOf = p => p.heroes?.[0] && (heroById.get(p.heroes[0].hero_id) || { name: p.heroes[0].name });
  const weights = loadWeights();
  computeScores(players, weights);
  const season = (status?.season_names || {})[status?.current_leaderboard_id] || 'temporada actual';
  root.append(el('div', { class: 'home-head' },
    el('span', { class: 'chip' }, season), el('span', { class: 'chip' }, status?.region || '—'),
    el('span', { class: 'chip' }, windowText(status?.stats_window) || 'sin ventana de stats'),
    el('span', { class: 'chip' }, status?.last_success ? `actualizado ${fmt.ago(status.last_success)}` : 'sin actualizar'),
    el('span', { class: 'chip' }, `${fmt.int(counts.players || 0)} jugadores · ${fmt.int(counts.matches || 0)} partidas`)));
  if (!counts.players) {
    root.append(el('section', { class: 'panel onboarding' }, sectionHead('Primeros pasos'),
      el('ol', { class: 'steps' },
        step(1, 'Descarga la leaderboard', 'Pulsa «Actualizar» en el panel lateral. La primera vez tarda unos minutos.'),
        step(2, 'Define los equipos', 'Edita equipos.txt (una línea por jugador: IDs y nombre del equipo) y recárgalo en Equipos.'),
        step(3, 'Analiza partidas', 'En Partidas, carga una por ID o sube su JSON para ver marcador, oro y minimapa.'))));
    return;
  }
  const topRow = (p, i, right) => el('button', { type: 'button', class: 'top-row', onclick: () => openProfile(p.id, ctx) },
    el('span', { class: 'n' }, i + 1), heroArt(heroOf(p), { size: 's56' }),
    el('span', { class: 'who' }, el('b', {}, p.name), el('span', {}, `${p.team || 'libre'} · ${fmt.int(p.stats.matches)} partidas · ${p.reliability}`)),
    right, el('span'));
  const reliable = players.filter(p => p.score != null && ['Media', 'Alta'].includes(p.reliability)).sort((a, b) => b.score - a.score);
  const top = el('section', { class: 'panel' }, sectionHead('Top 5 · score fiable', el('a', { href: '#jugadores', class: 'small' }, 'Ver todos →')),
    reliable.length ? el('div', { class: 'top-rows' }, reliable.slice(0, 5).map((p, i) => topRow(p, i, scoreRing(p.score, { lo: p._lo, hi: p._hi })))) : emptyState('Sin jugadores con 60+ partidas aún.'));
  const freeTop = players.filter(p => !p.team && p.score != null && p.reliability !== 'Insuficiente').sort((a, b) => b._lo - a._lo);
  const free = el('section', { class: 'panel' }, sectionHead('Libres destacados', el('span', { class: 'sub' }, 'por extremo bajo del score')),
    freeTop.length ? el('div', { class: 'top-rows' }, freeTop.slice(0, 5).map((p, i) => topRow(p, i, scoreRing(p.score, { lo: p._lo, hi: p._hi })))) : emptyState('No hay libres con muestra suficiente.'));
  const bc = (climb?.badge_climbers || []).filter(x => x.delta > 0).slice(0, 5);
  const lc = (climb?.climbers || []).slice(0, 5);
  const byId = new Map(players.map(p => [p.id, p]));
  const cl = el('section', { class: 'panel' }, sectionHead('Climbers · 7 d', el('a', { href: '#climbers', class: 'small' }, 'Ver todos →')));
  const list = bc.length ? bc.map(x => [byId.get(x.player_id), deltaChip(x.delta, { fmtFn: v => fmt.signed0(v) + ' MMR' })])
    : lc.map(x => [byId.get(x.player_id), el('span', { class: 'small muted' }, `#${x.from} → #${x.to}`)]);
  const lf = list.filter(([p]) => p);
  cl.append(lf.length ? el('div', { class: 'top-rows' }, lf.map(([p, r], i) => topRow(p, i, r))) : emptyState(climb?.warning || 'Aún no hay subidas que mostrar.', { ico: 'climbers' }));
  const tot = new Map();
  for (const p of players) for (const h of p.heroes || []) { const x = tot.get(h.hero_id) || { m: 0, w: 0 }; x.m += h.matches; x.w += h.wins; tot.set(h.hero_id, x); }
  const all = [...tot.values()].reduce((a, x) => a + x.m, 0) || 1;
  const strip = [...tot.entries()].sort((a, b) => b[1].m - a[1].m).slice(0, 8);
  const heroes = el('section', { class: 'panel' }, sectionHead('Héroes más jugados', el('a', { href: '#heroe', class: 'small' }, 'Por héroe →')),
    el('div', { class: 'hero-strip' }, strip.map(([id, x]) => el('a', { class: 'hs', href: `#heroe/${id}`, style: { textDecoration: 'none' } },
      heroArt(heroById.get(id) || {}, { size: 'card', label: true }), el('span', {}, `${fmt.pct(x.m / all)} pick · WR ${fmt.pct(x.w / x.m)}`)))));
  const mt = el('section', { class: 'panel' }, sectionHead('Últimas partidas', el('a', { href: '#partidas', class: 'small' }, 'Ver todas →')));
  if (!matches.length) mt.append(emptyState('Ninguna partida guardada. Cárgala por ID en Partidas.', { ico: 'partidas', action: el('a', { class: 'btn', href: '#partidas' }, 'Cargar partida') }));
  for (const m of matches.slice(0, 5)) mt.append(matchRow(m));
  root.append(el('div', { class: 'home-grid' }, top, cl, free, mt), heroes);
}

// Los 12 héroes con más partidas sumadas entre todos los jugadores; decorativo.
function heroMosaic(players, heroList) {
  const total = new Map();
  for (const p of players) for (const h of p.heroes || []) total.set(h.hero_id, (total.get(h.hero_id) || 0) + (h.matches || 0));
  const byId = new Map(heroList.map(h => [h.id, h]));
  const top = [...total.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)
    .map(([id]) => byId.get(id)).filter(Boolean);
  if (!top.length) return null;
  const box = el('div', { class: 'hero-mosaic', 'aria-hidden': 'true' });
  for (const h of top) { const img = heroPortrait(h, { size: 'lg', shape: 'card' }); img.alt = ''; box.append(img); }
  return box;
}

function step(n, title, text) {
  return el('li', {}, el('span', { class: 'step-n' }, n), el('div', {}, el('b', {}, title), el('p', { class: 'muted' }, text)));
}

export function matchRow(m) {
  const w = m.winning_team;
  return el('a', { class: 'match-row', href: `#partidas/${m.match_id}` },
    el('span', { class: `win-strip t${w}`, 'aria-hidden': 'true' }),
    el('span', { class: 'match-id' }, `#${m.match_id}`),
    el('span', { class: 'muted small' }, `${fmt.date(m.start_time)} · ${fmt.mmss(m.duration_s)}`),
    el('span', { class: `tag t${w}` }, `gana ${w === 0 ? 'Hidden King' : 'Archmother'}`));
}

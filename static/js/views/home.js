// Home: what the tool is, KPIs, this week's climbers, latest matches and quick links.
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
  const season = (status?.season_names || {})[status?.current_leaderboard_id] || 'current season';
  const chips = el('div', { class: 'home-head' },
    el('span', { class: 'chip' }, season), el('span', { class: 'chip' }, status?.region || '—'),
    el('span', { class: 'chip' }, windowText(status?.stats_window) || 'no stats window'),
    el('span', { class: 'chip' }, status?.last_success ? `updated ${fmt.ago(status.last_success)}` : 'not updated'),
    el('span', { class: 'chip' }, `${fmt.int(counts.players || 0)} players · ${fmt.int(counts.matches || 0)} matches`));
  // Poster-style header: headline with a highlighted word and cards of the most played heroes.
  const cards = heroCards(players, heroList);
  root.append(el('section', { class: 'hero home-hero' },
    el('div', { class: 'hero-text' },
      el('h1', {}, 'Find, compare and analyze Deadlock ', el('mark', { class: 'tag-word' }, 'players')),
      chips),
    el('div', { class: 'hero-visual' + (cards ? ' has-cards' : ''), 'aria-hidden': 'true' }, cards)));
  if (!counts.players) {
    root.append(el('section', { class: 'panel onboarding' }, sectionHead('Getting started'),
      el('ol', { class: 'steps' },
        step(1, 'Download the leaderboard', 'Press "Update" in the side panel. The first run takes a few minutes.'),
        step(2, 'Define the teams', 'Edit equipos.txt (one line per player: IDs and team name) and reload it in Teams.'),
        step(3, 'Analyze matches', 'In Matches, load one by ID or upload its JSON to see the scoreboard, gold and minimap.'))));
    return;
  }
  const topRow = (p, i, right) => el('button', { type: 'button', class: 'top-row', onclick: () => openProfile(p.id, ctx) },
    el('span', { class: 'n' }, i + 1), heroArt(heroOf(p), { size: 's56' }),
    el('span', { class: 'who' }, el('b', {}, p.name), el('span', {}, `${p.team || 'free agent'} · ${fmt.int(p.stats.matches)} matches · ${p.reliability}`)),
    right, el('span'));
  const reliable = players.filter(p => p.score != null && ['Medium', 'High'].includes(p.reliability)).sort((a, b) => b.score - a.score);
  const top = el('section', { class: 'panel' }, sectionHead('Top 5 · reliable score', el('a', { href: '#players', class: 'small' }, 'View all →')),
    reliable.length ? el('div', { class: 'top-rows' }, reliable.slice(0, 5).map((p, i) => topRow(p, i, scoreRing(p.score, { lo: p._lo, hi: p._hi })))) : emptyState('No players with 60+ matches yet.'));
  const freeTop = players.filter(p => !p.team && p.score != null && p.reliability !== 'Insufficient').sort((a, b) => b._lo - a._lo);
  const free = el('section', { class: 'panel' }, sectionHead('Standout free agents', el('span', { class: 'sub' }, 'by score lower bound')),
    freeTop.length ? el('div', { class: 'top-rows' }, freeTop.slice(0, 5).map((p, i) => topRow(p, i, scoreRing(p.score, { lo: p._lo, hi: p._hi })))) : emptyState('No free agents with a large enough sample.'));
  const bc = (climb?.badge_climbers || []).filter(x => x.delta > 0).slice(0, 5);
  const lc = (climb?.climbers || []).slice(0, 5);
  const byId = new Map(players.map(p => [p.id, p]));
  const cl = el('section', { class: 'panel' }, sectionHead('Climbers · 7 d', el('a', { href: '#climbers', class: 'small' }, 'View all →')));
  const list = bc.length ? bc.map(x => [byId.get(x.player_id), deltaChip(x.delta, { fmtFn: v => fmt.signed0(v) + ' MMR' })])
    : lc.map(x => [byId.get(x.player_id), el('span', { class: 'small muted' }, `#${x.from} → #${x.to}`)]);
  const lf = list.filter(([p]) => p);
  cl.append(lf.length ? el('div', { class: 'top-rows' }, lf.map(([p, r], i) => topRow(p, i, r))) : emptyState(climb?.warning || 'No climbs to show yet.', { ico: 'climbers' }));
  const tot = new Map();
  for (const p of players) for (const h of p.heroes || []) { const x = tot.get(h.hero_id) || { m: 0, w: 0 }; x.m += h.matches; x.w += h.wins; tot.set(h.hero_id, x); }
  const all = [...tot.values()].reduce((a, x) => a + x.m, 0) || 1;
  const strip = [...tot.entries()].sort((a, b) => b[1].m - a[1].m).slice(0, 8);
  const heroes = el('section', { class: 'panel' }, sectionHead('Most played heroes', el('a', { href: '#hero', class: 'small' }, 'By hero →')),
    el('div', { class: 'hero-strip' }, strip.map(([id, x]) => el('a', { class: 'hs', href: `#hero/${id}`, style: { textDecoration: 'none' } },
      heroArt(heroById.get(id) || {}, { size: 'card', label: true }), el('span', {}, `${fmt.pct(x.m / all)} pick · WR ${fmt.pct(x.w / x.m)}`)))));
  const mt = el('section', { class: 'panel' }, sectionHead('Latest matches', el('a', { href: '#matches', class: 'small' }, 'View all →')));
  if (!matches.length) mt.append(emptyState('No matches saved. Load one by ID in Matches.', { ico: 'matches', action: el('a', { class: 'btn', href: '#matches' }, 'Load a match') }));
  for (const m of matches.slice(0, 5)) mt.append(matchRow(m));
  root.append(el('div', { class: 'home-grid' }, top, cl, free, mt), heroes);
}

// The 8 heroes with the most matches summed over all players, as tilted cards; decorative.
function heroCards(players, heroList) {
  const total = new Map();
  for (const p of players) for (const h of p.heroes || []) total.set(h.hero_id, (total.get(h.hero_id) || 0) + (h.matches || 0));
  const byId = new Map(heroList.map(h => [h.id, h]));
  const top = [...total.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([id]) => byId.get(id)).filter(Boolean);
  if (!top.length) return null;
  const box = el('div', { class: 'hero-cards tilt-cards' });
  for (const h of top) box.append(heroPortrait(h, { size: 'lg', shape: 'card', decorative: true }));
  return box;
}

function step(n, title, text) {
  return el('li', {}, el('span', { class: 'step-n' }, n), el('div', {}, el('b', {}, title), el('p', { class: 'muted' }, text)));
}

export function matchRow(m) {
  const w = m.winning_team;
  return el('a', { class: 'match-row', href: `#matches/${m.match_id}` },
    el('span', { class: `win-strip t${w}`, 'aria-hidden': 'true' }),
    el('span', { class: 'match-id' }, `#${m.match_id}`),
    el('span', { class: 'muted small' }, `${fmt.date(m.start_time)} · ${fmt.mmss(m.duration_s)}`),
    el('span', { class: `tag t${w}` }, `${w === 0 ? 'Hidden King' : 'Archmother'} won`));
}

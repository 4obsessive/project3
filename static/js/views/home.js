// Inicio: qué es la herramienta, KPIs, climbers de la semana, últimas partidas y accesos rápidos.
import { api, getPlayers, getHeroes } from '../api.js';
import { el, fmt } from '../util.js';
import { icon } from '../icons.js';
import { heroPortrait } from '../art.js';
import { openProfile } from './profile.js';

const LINKS = [
  ['jugadores', 'Jugadores', 'Compara y filtra a todos los jugadores seguidos.'],
  ['heroe', 'Por héroe', 'Los mejores con cada héroe este mes.'],
  ['climbers', 'Climbers', 'Quién sube más rápido en el ranking.'],
  ['equipos', 'Equipos', 'Plantillas y jugadores libres.'],
  ['partidas', 'Partidas', 'Marcador, oro, objetivos y minimapa.'],
  ['informe', 'Informe', 'Estadísticas de un equipo para preparar un partido.'],
];

export async function render(root, ctx) {
  const [status, players, matches, climb, heroList] = await Promise.all([
    api.get('/api/status').catch(() => ctx.status),
    getPlayers().catch(() => []),
    api.get('/api/matches').catch(() => []),
    api.get('/api/climbers?days=7').catch(() => null),
    getHeroes().catch(() => []),
  ]);
  const counts = status?.counts || {};
  const empty = !counts.players;

  const cards = heroCards(players, heroList);
  root.append(el('section', { class: 'hero' },
    el('div', { class: 'hero-text' },
      el('span', { class: 'eyebrow' }, `Scouting · ${status?.region || 'región'} · ${(status?.season_names || {})[status?.current_leaderboard_id] || 'temporada actual'}`),
      el('h1', {}, 'Encuentra, compara y analiza ', el('mark', { class: 'tag-word' }, 'jugadores'), ' de Deadlock'),
      el('p', {}, 'Sigue la leaderboard de tu región, detecta jugadores libres y en racha, y revisa partidas y rivales con gráficas claras. Todo se queda en tu ordenador.'),
      el('div', { class: 'row' },
        el('a', { class: 'btn primary', href: '#jugadores' }, icon('jugadores'), 'Ver jugadores'),
        el('a', { class: 'btn', href: '#partidas' }, icon('partidas'), 'Analizar una partida'))),
    el('div', { class: 'hero-art' + (cards ? ' has-cards' : ''), 'aria-hidden': 'true' }, cards)));

  const kpi = (ic, value, label, sub) => el('div', { class: 'kpi' }, el('span', { class: 'kpi-ico' }, icon(ic)),
    el('div', {}, el('div', { class: 'kpi-val' }, value), el('div', { class: 'kpi-lbl' }, label), sub ? el('div', { class: 'kpi-sub' }, sub) : null));
  const free = players.filter(p => !p.team).length;
  root.append(el('div', { class: 'kpis' },
    kpi('jugadores', fmt.int(counts.players || 0), 'Jugadores seguidos', `${fmt.int(free)} libres`),
    kpi('partidas', fmt.int(counts.matches || 0), 'Partidas analizadas', matches[0] ? `última: ${fmt.date(matches[0].start_time)}` : 'ninguna aún'),
    kpi('clock', status?.last_success ? fmt.ago(status.last_success) : 'Pendiente', 'Última actualización', status?.running ? 'actualizando ahora…' : status?.next_run ? `próxima ${fmt.datetime(status.next_run)}` : null),
    kpi('db', fmt.int(counts.snapshots || 0), 'Snapshots del ranking', 'base para los climbers')));

  if (empty) {
    root.append(el('section', { class: 'panel onboarding' }, el('h2', { class: 'section-title' }, 'Primeros pasos'),
      el('ol', { class: 'steps' },
        step(1, 'Descarga la leaderboard', 'Pulsa «Actualizar» arriba a la derecha. La primera vez tarda unos minutos.'),
        step(2, 'Define los equipos', 'Edita equipos.txt (una línea por jugador: IDs y nombre del equipo) y recárgalo en Equipos.'),
        step(3, 'Analiza partidas', 'En Partidas, carga una por ID o sube su JSON para ver marcador, oro y minimapa.'))));
  }

  const grid = el('div', { class: 'home-grid' });
  // climbers
  const cl = el('section', { class: 'panel' }, el('div', { class: 'section-head' }, el('h2', { class: 'section-title' }, 'Climbers de la semana'), el('a', { href: '#climbers' }, 'Ver todos →')));
  const list = (climb?.climbers || []).slice().sort((a, b) => b.delta - a.delta).slice(0, 5);
  if (!list.length) cl.append(el('p', { class: 'muted' }, climb?.warning || 'Aún no hay subidas que mostrar.'));
  else {
    const max = Math.max(...list.map(c => c.delta));
    cl.append(el('ol', { class: 'climb-list' }, list.map(c => el('li', {},
      el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(c.player_id, ctx) }, c.name),
      el('span', { class: 'climb-bar', 'aria-hidden': 'true' }, el('span', { style: { width: (100 * c.delta / max) + '%' } })),
      el('span', { class: 'climb-delta' }, `+${c.delta}`), el('span', { class: 'muted small' }, `#${c.from} → #${c.to}`)))));
  }
  // partidas
  const mt = el('section', { class: 'panel' }, el('div', { class: 'section-head' }, el('h2', { class: 'section-title' }, 'Últimas partidas'), el('a', { href: '#partidas' }, 'Ver todas →')));
  if (!matches.length) mt.append(el('p', { class: 'muted' }, 'Ninguna partida guardada. Cárgala por ID en Partidas.'));
  for (const m of matches.slice(0, 5)) mt.append(matchRow(m));
  grid.append(cl, mt);
  root.append(grid);

  root.append(el('h2', { class: 'section-title' }, 'Accesos rápidos'),
    el('div', { class: 'quick', role: 'navigation', 'aria-label': 'Accesos rápidos' }, LINKS.map(([v, t, d]) => el('a', { href: '#' + v, class: 'quick-card' },
      el('span', { class: 'quick-ico' }, icon(v)), el('span', { class: 'quick-t' }, t), el('span', { class: 'quick-d' }, d)))));
}

// Los 8 héroes con más partidas sumadas entre todos los jugadores, como cartas inclinadas; decorativo.
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
  return el('a', { class: 'match-row', href: `#partidas/${m.match_id}` },
    el('span', { class: `win-strip t${w}`, 'aria-hidden': 'true' }),
    el('span', { class: 'match-id' }, `#${m.match_id}`),
    el('span', { class: 'muted small' }, `${fmt.date(m.start_time)} · ${fmt.mmss(m.duration_s)}`),
    el('span', { class: `tag t${w}` }, `gana ${w === 0 ? 'Hidden King' : 'Archmother'}`));
}

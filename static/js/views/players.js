import { api, getPlayers, getHeroes } from '../api.js';
import { el, fmt, dataTable, store, csvDownload, scaler } from '../util.js';
import { icon } from '../icons.js';
import { computeScores, DEFAULT_WEIGHTS, WEIGHT_LABELS, loadWeights, saveWeights } from '../score.js';
import { heroArt, rankEmblem, scoreRing, wrBar, confidencePips, roleChips, deltaChip, statTile, getRanks, windowText, roleColor, countUp } from '../ui.js';
import { openProfile } from './profile.js';

export const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];
const ROLES = ['Carry', 'Off-carry', 'Initiator', 'Frontline', 'Catcher', 'Support'];
const STEPS = [0, 20, 60, 150];

export async function render(root, ctx) {
  const [players, climb, heroList, ranks] = await Promise.all([getPlayers(true), api.get('/api/climbers?days=7').catch(() => null), getHeroes().catch(() => []), getRanks()]);
  const heroById = new Map(heroList.map(h => [h.id, h]));
  let mode = store.get('playersMode', 'table');
  const f = { q: '', team: 'all', role: '', minMatches: 0, newDays: 0, status: '', source: 'all', conservative: false, ...store.get('playerFilters', {}) };
  const weights = loadWeights();
  const now = Date.now() / 1000;
  const hero = p => p.heroes?.[0] && (heroById.get(p.heroes[0].hero_id) || { id: p.heroes[0].hero_id, name: p.heroes[0].name });

  // ---------------------------------------------------------------- barra de filtros
  const search = el('input', { type: 'search', class: 'search', 'aria-label': 'Buscar jugador', placeholder: 'Buscar nombre, equipo, ID…', value: f.q });
  search.addEventListener('input', () => { f.q = search.value; update(); });
  const roleBtns = ROLES.map(r => {
    const b = el('button', { type: 'button', class: 'toggle-chip', 'aria-pressed': String(f.role === r), style: { '--role': roleColor(r) },
      onclick: () => { f.role = f.role === r ? '' : r; roleBtns.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.role === f.role))); update(); } },
      el('i', { 'aria-hidden': 'true' }), r);
    b.dataset.role = r;
    return b;
  });
  const freeBtn = el('button', { type: 'button', class: 'toggle-chip', 'aria-pressed': String(f.team === 'free'),
    onclick: () => { f.team = f.team === 'free' ? 'all' : 'free'; freeBtn.setAttribute('aria-pressed', String(f.team === 'free')); update(); } }, 'Libres');
  const stepLabel = el('span', { 'aria-live': 'polite' });
  const paintStep = () => { stepLabel.textContent = f.minMatches ? `≥ ${f.minMatches} partidas` : 'Todas'; };
  const stepBy = d => { const i = Math.max(0, STEPS.findIndex(x => x >= f.minMatches)); f.minMatches = STEPS[Math.max(0, Math.min(STEPS.length - 1, i + d))]; paintStep(); update(); };
  const stepper = el('span', { class: 'stepper', role: 'group', 'aria-label': 'Partidas mínimas' },
    el('button', { type: 'button', 'aria-label': 'Menos partidas mínimas', onclick: () => stepBy(-1) }, '−'), stepLabel,
    el('button', { type: 'button', 'aria-label': 'Más partidas mínimas', onclick: () => stepBy(1) }, '+'));
  paintStep();
  const modeBtn = (m, label) => {
    const b = el('button', { type: 'button', class: 'seg' + (mode === m ? ' active' : ''), 'aria-pressed': String(mode === m), title: label,
      onclick: () => { mode = m; store.set('playersMode', m); for (const x of b.parentNode.children) { const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-pressed', String(on)); } update(); } },
      icon(m === 'table' ? 'list' : 'grid'), el('span', { class: 'btn-label' }, label));
    return b;
  };
  const select = (key, options) => {
    const s = el('select', { 'aria-label': key }, options.map(([v, l]) => el('option', { value: v, selected: String(f[key]) === String(v) }, l)));
    s.addEventListener('change', () => { f[key] = s.value; update(); });
    return s;
  };
  // popover: filtros avanzados + pesos del score
  const wvals = {};
  const wrows = WEIGHT_LABELS.map(([k, label]) => {
    const val = el('span', { class: 'mono' }, weights[k]);
    const r = el('input', { type: 'range', min: 0, max: 100, value: weights[k], 'aria-label': `Peso: ${label}` });
    r.addEventListener('input', () => { weights[k] = +r.value; val.textContent = r.value; saveWeights(weights); computeScores(players, weights); update(); });
    wvals[k] = [r, val];
    return [el('span', {}, label), r, val];
  });
  const consv = el('input', { type: 'checkbox', checked: f.conservative });
  consv.addEventListener('change', () => { f.conservative = consv.checked; update(); });
  const pop = el('div', { class: 'popover', id: 'pl-pop', hidden: true, role: 'dialog', 'aria-label': 'Filtros y pesos' },
    el('h4', {}, 'Filtros'),
    el('div', { class: 'grid-form' },
      el('span', {}, 'Equipo'), select('team', [['all', 'Todos'], ['free', 'Libres'], ['team', 'Con equipo']]), el('span'),
      el('span', {}, 'Nuevos en'), select('newDays', [[0, '—'], [7, '7 días'], [30, '30 días']]), el('span'),
      el('span', {}, 'Estado'), select('status', [['', 'Cualquiera'], ...STATUSES.map(s => [s, s])]), el('span'),
      el('span', {}, 'Origen'), select('source', [['all', 'Todos'], ['current', 'Temporada actual'], ['lb', 'Alguna leaderboard'], ['off', 'Fuera de leaderboard']]), el('span')),
    el('h4', {}, 'Pesos del score'),
    el('p', { class: 'muted small' }, 'Cada componente es un percentil frente a los jugadores con ≥20 partidas: winrate ajustado por muestra; KDA, daño, oro y objetivos relativos a la media de los jugadores seguidos en los mismos héroes; variedad = nº efectivo de héroes con ≥5 partidas.'),
    el('div', { class: 'grid-form' }, wrows),
    el('label', { class: 'check' }, consv, 'Orden conservador (ordena por el extremo bajo de la banda del score)'),
    el('div', { class: 'row', style: { marginTop: '12px' } }, el('button', { type: 'button', onclick: () => {
      Object.assign(weights, DEFAULT_WEIGHTS); saveWeights(weights);
      for (const [k, [r, v]] of Object.entries(wvals)) { r.value = weights[k]; v.textContent = weights[k]; }
      computeScores(players, weights); update();
    } }, 'Restablecer pesos')));
  const popBtn = el('button', { type: 'button', class: 'toggle-chip', 'aria-expanded': 'false', 'aria-controls': 'pl-pop',
    onclick: () => { pop.hidden = !pop.hidden; popBtn.setAttribute('aria-expanded', String(!pop.hidden)); if (!pop.hidden) pop.querySelector('select')?.focus(); } },
    icon('filter'), 'Filtros y pesos');
  pop.addEventListener('keydown', e => { if (e.key === 'Escape') { pop.hidden = true; popBtn.setAttribute('aria-expanded', 'false'); popBtn.focus(); } });
  document.addEventListener('click', e => { if (!pop.hidden && !e.target.closest('.popover-wrap')) { pop.hidden = true; popBtn.setAttribute('aria-expanded', 'false'); } });
  const filterbar = el('div', { class: 'filterbar' }, search, ...roleBtns, freeBtn, stepper,
    el('span', { class: 'popover-wrap' }, popBtn, pop),
    el('div', { class: 'segmented', role: 'group', 'aria-label': 'Vista' }, modeBtn('table', 'Tabla'), modeBtn('cards', 'Tarjetas')));

  computeScores(players, weights);
  const muted = p => p.reliability === 'Insuficiente';
  let sc = {};
  const heat = (k, get) => p => muted(p) ? 'dim' : sc[k]?.(get(p));
  const scoreKey = p => f.conservative ? p._lo : p.score;
  const cols = [
    { key: 'rank', label: 'Rank', num: true, keep: true, title: 'Posición en la leaderboard actual y rango (badge)',
      sort: p => p.rank ?? (p.badge ? 10000 - p.badge : null),
      render: p => el('span', { class: 'rank-cell' }, el('span', { class: 'pos' + (p.rank && p.rank <= 3 ? ' top' : '') }, p.rank ? '#' + p.rank : '–'), p.badge ? rankEmblem(p.badge, ranks, { label: false }) : null) },
    { key: 'name', label: 'Jugador', keep: true, sort: p => p.name.toLowerCase(), render: p => playerCell(p, hero(p), heroById) },
    { key: 'role', label: 'Rol', sortable: false, keep: true, render: p => roleChips(p) },
    { key: 'matches', label: 'Partidas', num: true, sort: p => p.stats.matches, render: p => fmt.int(p.stats.matches) },
    { key: 'winrate', label: 'WR', num: true, title: 'Winrate (con intervalo de confianza del 95 %). Se ordena por el winrate ajustado por muestra.',
      sort: p => p.stats.wr_adj, render: p => wrBar(p.stats.winrate, { lo: p.stats.wr_lo, hi: p.stats.wr_hi, muted: muted(p), n: p.stats.matches }) },
    { key: 'kda', label: 'KDA idx', num: true, title: 'KDA relativo a la media de jugadores seguidos en los mismos héroes (1.00 = media), ajustado por muestra',
      sort: p => p.stats.idx_kda, cellClass: heat('kda', p => p.stats.idx_kda), render: p => el('span', { title: `KDA bruto ${fmt.dec(p.stats.kda)}` }, fmt.dec(p.stats.idx_kda)) },
    { key: 'dmg', label: 'Daño/min', num: true, sort: p => p.stats.dmg_per_min, cellClass: heat('dmg', p => p.stats.idx_dmg), render: p => fmt.int(p.stats.dmg_per_min) },
    { key: 'nw', label: 'Oro/min', num: true, sort: p => p.stats.nw_per_min, cellClass: heat('nw', p => p.stats.idx_nw), render: p => fmt.int(p.stats.nw_per_min) },
    { key: 'form', label: 'Forma 7 d', num: true, title: 'Winrate ajustado de los últimos 7 días menos el del periodo',
      sort: p => p.stats.form, render: p => p.stats.matches_7d ? el('span', {}, deltaChip(p.stats.form, { title: `${p.stats.matches_7d} partidas en 7 días` })) : el('span', { class: 'muted small' }, 'inactivo') },
    { key: 'conf', label: 'Confianza', sort: p => p.stats.matches, render: p => confidencePips(p.reliability, { wr: p.stats.winrate, n: p.stats.matches, lo: p.stats.wr_lo, hi: p.stats.wr_hi }) },
    { key: 'score', label: 'Score', num: true, sort: scoreKey, render: p => el('span', {}, scoreRing(p.score, { lo: p._lo, hi: p._hi, provisional: p.provisional })) },
    { key: 'status', label: 'Estado', keep: true, sort: p => p.manual.status === 'pendiente' ? '' : p.manual.status,
      render: p => p.manual.status === 'pendiente' ? '' : el('span', { class: 'status-pill s-' + p.manual.status.replace(/\s+/g, '-') }, p.manual.status) },
  ];
  const table = dataTable(cols, [], { sortKey: 'score', asc: false, hideEmpty: true, animate: true, label: 'Jugadores', onRowClick: p => openProfile(p.id, ctx),
    emptyText: players.length ? 'Sin resultados con estos filtros.' : 'Todavía no hay jugadores. La primera actualización se lanza sola al arrancar; mira el progreso en el panel lateral.' });
  const exportBtn = el('button', { type: 'button', onclick: () => csvDownload('jugadores.csv', [
    { key: 'rank', label: 'rank' }, { key: 'name', label: 'nombre' }, { label: 'account_id', csv: p => p.primary_account_id },
    { label: 'equipo', csv: p => p.team || '' }, { label: 'roles', csv: p => p.role_text }, { label: 'partidas', csv: p => p.stats.matches },
    { label: 'winrate', csv: p => p.stats.winrate?.toFixed(3) }, { label: 'wr_ajustado', csv: p => p.stats.wr_adj?.toFixed(3) },
    { label: 'wr_ic95', csv: p => p.stats.wr_lo == null ? '' : `${p.stats.wr_lo.toFixed(3)}-${p.stats.wr_hi.toFixed(3)}` },
    { label: 'kda', csv: p => p.stats.kda?.toFixed(2) }, { label: 'kda_idx', csv: p => p.stats.idx_kda?.toFixed(2) },
    { label: 'dano_partida', csv: p => p.stats.damage_per_match?.toFixed(0) }, { label: 'dano_min', csv: p => p.stats.dmg_per_min?.toFixed(0) },
    { label: 'oro_min', csv: p => p.stats.nw_per_min?.toFixed(0) }, { label: 'badge', csv: p => p.badge ?? '' },
    { label: 'fiabilidad', csv: p => p.reliability },
    { label: 'score', csv: p => p.score?.toFixed(1) }, { label: 'estado', csv: p => p.manual.status }], filtered()) }, 'Exportar CSV');

  function filtered() {
    const q = f.q.trim().toLowerCase();
    return players.filter(p => {
      if (q && !(p.name.toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q) || p.accounts.some(a => String(a.account_id).includes(q)))) return false;
      if (f.team === 'free' && p.team) return false;
      if (f.team === 'team' && !p.team) return false;
      if (f.role && !(p.roles.includes(f.role) || p.role_primary === f.role)) return false;
      if (f.minMatches && p.stats.matches < f.minMatches) return false;
      if (f.status && p.manual.status !== f.status) return false;
      if (f.source === 'current' && p.rank == null) return false;
      if (f.source === 'lb' && !Object.keys(p.ranks).length) return false;
      if (f.source === 'off' && Object.keys(p.ranks).length) return false;
      if (+f.newDays) {
        if (!p.first_in_current || p.first_in_current <= p.history_start) return false;
        if (p.first_in_current < now - f.newDays * 86400) return false;
      }
      return true;
    });
  }
  const tiles = el('div', { class: 'stat-tiles' });
  const cards = el('div', { class: 'pcards' });
  const meta = el('div', { class: 'list-meta' });
  function update() {
    store.set('playerFilters', f);
    const rows = filtered();
    const ref = rows.filter(p => !muted(p));
    sc = { kda: scaler(ref.map(p => p.stats.idx_kda)), dmg: scaler(ref.map(p => p.stats.idx_dmg)), nw: scaler(ref.map(p => p.stats.idx_nw)) };
    table.hidden = mode !== 'table'; cards.hidden = mode !== 'cards';
    if (mode === 'table') table.update(rows); else renderCards(rows);
    const win = players[0]?.window;
    meta.replaceChildren(el('span', {}, `${rows.length} de ${players.length} jugadores`), el('span', {}, '·'), el('span', {}, windowText(win)),
      el('span', {}, '·'), el('span', {}, ctx.status?.region || ''), el('span', { class: 'spacer' }), exportBtn);
  }
  function renderCards(rows) {
    cards.innerHTML = '';
    const sorted = rows.slice().sort((a, b) => (scoreKey(b) ?? -1) - (scoreKey(a) ?? -1) || (a.rank ?? 1e9) - (b.rank ?? 1e9));
    if (!sorted.length) cards.append(el('div', { class: 'empty' }, 'Sin resultados con estos filtros.'));
    for (const p of sorted.slice(0, 120)) cards.append(playerCard(p, hero(p), ranks, ctx));
    if (sorted.length > 120) cards.append(el('div', { class: 'muted small' }, `Mostrando 120 de ${sorted.length}; usa los filtros o la vista de tabla.`));
  }
  renderTiles(tiles, players, climb, hero, ctx);
  root.append(tiles, filterbar, meta, table, cards);
  update();
}

function playerCell(p, h, heroById) {
  const pic = p.avatar ? el('img', { class: 'avatar-img', src: p.avatar, alt: '', loading: 'lazy' }) : heroArt(h, { size: 'round' });
  if (p.avatar) pic.addEventListener('error', () => pic.replaceWith(heroArt(h, { size: 'round' })));
  const minis = (p.heroes || []).slice(0, 3).map(x => heroArt(heroById.get(x.hero_id) || { name: x.name }, { size: 'mini' }));
  return el('span', { class: 'pl-cell' }, pic,
    el('span', { class: 'who' }, el('span', { class: 'nm' }, p.name),
      el('span', { class: 'sub' }, p.team ? el('span', { title: p.team_source }, p.team) : el('span', { class: 'free' }, 'libre'),
        el('span', { class: 'mini-heroes', title: (p.heroes || []).slice(0, 3).map(x => `${x.name} (${x.matches})`).join(', ') }, minis))));
}

function playerCard(p, h, ranks, ctx) {
  const s = p.stats;
  return el('button', { type: 'button', class: 'pcard', onclick: () => openProfile(p.id, ctx), 'aria-label': `Abrir perfil de ${p.name}` },
    el('div', { class: 'pcard-art' }, heroArt(h, { size: 'card' }),
      scoreRing(p.score, { lo: p._lo, hi: p._hi, provisional: p.provisional }),
      el('div', { class: 'pcard-head' },
        el('span', { class: 'pcard-name' }, p.name),
        el('span', { class: 'row', style: { gap: '8px' } }, p.badge ? rankEmblem(p.badge, ranks) : null,
          el('span', { class: 'small muted' }, p.rank ? '#' + p.rank : ''), p.team ? el('span', { class: 'small' }, p.team) : el('span', { class: 'small', style: { color: 'var(--spirit)' } }, 'libre')))),
    el('div', { class: 'pcard-body' },
      el('div', { class: 'pcard-stats' },
        el('div', {}, el('b', {}, fmt.int(s.matches)), el('span', {}, 'partidas')),
        el('div', {}, el('b', {}, fmt.pct(s.winrate)), el('span', {}, s.wr_lo != null ? `IC ${Math.round(s.wr_lo * 100)}–${Math.round(s.wr_hi * 100)}%` : 'winrate')),
        el('div', {}, el('b', {}, fmt.dec(s.idx_kda)), el('span', {}, 'KDA idx'))),
      roleChips(p)));
}

function renderTiles(box, players, climb, hero, ctx) {
  const tile = (label, p, value, sub, extra = {}) => statTile(label, p ? value : '–', {
    sub: p ? sub : 'Sin datos aún', art: p ? heroArt(hero(p), { size: 'card', kind: 'card' }) : null,
    onClick: p ? () => openProfile(p.id, ctx) : null, ...extra });
  const reliable = players.filter(p => p.score_default != null && ['Media', 'Alta'].includes(p.reliability));
  const best = reliable.slice().sort((a, b) => b.score - a.score)[0];
  const bestWr = players.filter(p => p.stats.wr_adj != null && p.reliability !== 'Insuficiente').sort((a, b) => b.stats.wr_adj - a.stats.wr_adj)[0];
  const hot = players.filter(p => p.stats.matches_7d >= 5 && p.stats.form != null).sort((a, b) => b.stats.form - a.stats.form)[0];
  let climber = null, csub = '';
  const bc = climb?.badge_climbers?.find(x => x.delta > 0);
  const lc = climb?.climbers?.[0];
  if (bc) { climber = players.find(p => p.id === bc.player_id); csub = `+${fmt.int(bc.delta)} de progreso de rango`; }
  else if (lc) { climber = players.find(p => p.id === lc.player_id); csub = `#${lc.from} → #${lc.to}`; }
  const scoreVal = el('span');
  if (best) countUp(scoreVal, best.score);
  box.append(
    tile('Mejor score fiable', best, scoreVal, best ? `${best.name} · ${fmt.int(best.stats.matches)} partidas` : '', { tone: 'gold' }),
    tile('Mejor WR ajustado', bestWr, bestWr ? fmt.pct(bestWr.stats.wr_adj) : '–', bestWr ? `${bestWr.name} · ${fmt.pct(bestWr.stats.winrate)} en ${fmt.int(bestWr.stats.matches)}` : ''),
    tile('En racha · 7 d', hot, hot ? fmt.signed(hot.stats.form * 100, 0) + ' pp' : '–', hot ? `${hot.name} · ${hot.stats.wins_7d}/${hot.stats.matches_7d} en 7 días` : ''),
    tile('Mayor subida', climber, climber ? (bc ? '▲ ' + fmt.int(bc.delta) : '▲ ' + (lc.from - lc.to)) : '–', climber ? `${climber.name} · ${csub}` : 'hace falta más historial'));
}

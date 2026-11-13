import { api, getHeroes } from '../api.js';
import { el, fmt, formatValue, dataTable, toast, spinner, csvDownload, store, errorBox } from '../util.js';
import { MapView, COLORS, legend, loadMapInfo } from '../map.js';
import { timeline } from '../charts.js';
import { renderExplorer } from './explorer.js';
import { openProfile } from './profile.js';
import { icon } from '../icons.js';
import { heroPortrait, objectiveImg, objectiveSrc, laneStyle, laneChip } from '../art.js';
import { matchRow } from './home.js';

export async function render(root, ctx) {
  const idInput = el('input', { id: 'match-id', inputmode: 'numeric', placeholder: 'Match ID', 'aria-label': 'Match ID', style: { width: '140px' } });
  const fileInput = el('input', { type: 'file', id: 'match-file', class: 'sr-only', accept: '.json,application/json' });
  const list = el('div');
  const detail = el('div');
  const load = async () => {
    const id = idInput.value.trim();
    if (!id) return;
    btn.disabled = true; btn.textContent = 'Downloading…';
    try { await api.post('/api/matches/load', { match_id: id }); await refresh(); location.hash = `#partidas/${id}`; }
    catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; btn.textContent = 'Load'; }
  };
  const btn = el('button', { class: 'primary', onclick: load }, 'Load');
  idInput.addEventListener('keydown', e => { if (e.key === 'Enter') load(); });
  fileInput.addEventListener('change', async () => {
    const f = fileInput.files[0]; if (!f) return;
    try { const r = await api.post('/api/matches/upload', await f.text()); toast(`Match ${r.match_id} saved`); await refresh(); location.hash = `#partidas/${r.match_id}`; }
    catch (e) { toast(e.message, true); }
    fileInput.value = '';
  });
  root.append(el('div', { class: 'split' },
    el('div', {},
      el('div', { class: 'panel' }, el('h3', {}, 'Load match'), el('div', { class: 'row' }, idInput, btn),
        el('div', { class: 'muted small', style: { margin: '10px 0 4px' } }, 'or upload its JSON (deadlock-api metadata):'),
        el('label', { for: 'match-file', class: 'filepick' }, icon('upload'), el('span', {}, 'Choose JSON file…')), fileInput),
      el('div', { class: 'panel' }, el('h3', {}, 'Saved'), list)),
    detail));

  async function refresh() {
    const ms = await api.get('/api/matches');
    list.innerHTML = '';
    if (!ms.length) list.append(el('div', { class: 'muted small' }, 'None yet.'));
    for (const m of ms) {
      list.append(matchRow(m));
    }
  }
  await refresh();
  const id = ctx.params[0];
  if (id) showMatch(detail, id, ctx);
  else detail.append(el('div', { class: 'panel empty' }, icon('partidas', 'big'), el('p', {}, 'Pick a saved match or load a new one by ID to see its scoreboard, gold difference and minimap.')));
}

async function showMatch(root, id, ctx) {
  clearTimeout(demoTimer); demoTimer = null;
  const gen = ++matchGen;
  root.innerHTML = ''; root.append(spinner('Loading match…'));
  let m;
  try { m = await api.get(`/api/matches/${id}`); } catch (e) { if (gen !== matchGen) return; root.innerHTML = ''; root.append(errorBox(e.message, () => showMatch(root, id, ctx), 'Could not load the match')); return; }
  if (gen !== matchGen) return;
  try { const hs = await getHeroes(); heroById = new Map(hs.map(h => [h.id, h])); } catch { heroById = new Map(); }
  if (gen !== matchGen) return; // another match was opened in the meantime
  root.innerHTML = '';
  const TN = m.team_names;
  const tname = t => `${TN[t]} (${t})`;
  const verified = m.team_names_verified ? '' : ' · side names according to third-party sources (team 0 = base at the bottom, verified)';
  const head = scoreboard(m, TN, verified);
  const gold = goldPanel(m, tname);
  const tabs = el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Match sections' });
  const body = el('div', { class: 'panel', role: 'tabpanel', id: 'match-tabpanel', tabindex: '0' });
  root.append(head, gold, tabs, body);
  const views = {
    'Summary': () => resumen(body, m, tname, ctx),
    'Objectives': () => objetivos(body, m, tname),
    'Midboss': () => midboss(body, m, tname),
    'Laning phase': () => faseLineas(body, m, tname),
    'Players': () => jugadores(body, m, tname),
    'Economy': () => economia(body, m, tname),
    'Minimap': () => minimapa(body, m, tname),
    'Explorer': () => renderExplorer(body, m.match_id),
  };
  let current = store.get('matchTab', 'Summary');
  if (!views[current]) current = 'Summary';
  const select = b => {
    current = b.dataset.tab; store.set('matchTab', current);
    for (const x of tabs.children) { const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; }
    body.setAttribute('aria-labelledby', b.id);
    body.innerHTML = ''; views[current]();
  };
  for (const name of Object.keys(views)) {
    const on = name === current;
    const b = el('button', { type: 'button', role: 'tab', id: tabId(name), 'aria-controls': 'match-tabpanel', 'aria-selected': String(on), tabindex: on ? '0' : '-1', class: on ? 'active' : '', onclick: () => select(b) }, name);
    b.dataset.tab = name;
    tabs.append(b);
  }
  // arrow keys move between tabs (ARIA tabs pattern)
  tabs.addEventListener('keydown', e => {
    const list = [...tabs.children], i = list.indexOf(document.activeElement);
    if (i < 0) return;
    const j = e.key === 'ArrowRight' ? (i + 1) % list.length : e.key === 'ArrowLeft' ? (i - 1 + list.length) % list.length : e.key === 'Home' ? 0 : e.key === 'End' ? list.length - 1 : -1;
    if (j < 0) return;
    e.preventDefault(); list[j].focus(); select(list[j]);
  });
  body.setAttribute('aria-labelledby', tabId(current));
  views[current]();
  // when the demo finishes only the open tab is repainted, and only if it depends on it (Objectives: KOTH; Midboss)
  scheduleDemoRefresh(root, id, gen, m, () => {
    if (!DEMO_TABS.has(current)) return;
    body.innerHTML = ''; views[current]();
  });
}

const tabId = name => 'tab-' + name.toLowerCase().replace(/\s+/g, '-');
let heroById = new Map();
let demoTimer = null;
let matchGen = 0;
const DEMO_TABS = new Set(['Objectives', 'Midboss', 'Laning phase', 'Players', 'Minimap']);
const LANE_POLLS = 15; // demo ready but no lane data: at most 15 polls (5 min)
/** While the demo is pending, polls /api/matches/{id}/demo in the background every 20 s (no repaint);
 *  when it stops being pending it updates m.demo/m.comeback and calls onReady. Stops when leaving the match. */
function scheduleDemoRefresh(root, id, gen, m, onReady, tries = 0) {
  clearTimeout(demoTimer); demoTimer = null;
  const pending = m.demo?.state === 'pending';
  // demo ready but lane phase not filled in yet: keep polling for a limited time
  const needLane = m.demo?.state === 'done' && m.lane_phase?.source !== 'demo' && !m.lane_phase?.demo_incompleto && tries < LANE_POLLS;
  if (!pending && !needLane) return;
  const still = () => gen === matchGen && root.isConnected
    && location.hash.slice(1).split(/[/?]/)[0] === 'partidas' && location.hash.slice(1).split(/[/?]/)[1] === String(id);
  demoTimer = setTimeout(async () => {
    demoTimer = null;
    if (!still()) return;
    let r = null;
    try { r = await api.get(`/api/matches/${id}/demo`); } catch { /* network failure: retried on the next cycle */ }
    if (!still()) return;
    if (r) {
      const changed = r.demo?.state !== m.demo?.state || r.lane_phase?.source !== m.lane_phase?.source
        || r.fights?.koth_known !== m.fights?.koth_known;
      m.demo = r.demo; m.comeback = r.comeback;
      if (r.lane_phase !== undefined) { m.lane_phase = r.lane_phase; m.player_stats = r.player_stats; }
      if (r.fights !== undefined) m.fights = r.fights;
      if (changed) onReady();
    }
    scheduleDemoRefresh(root, id, gen, m, onReady, m.demo?.state === 'done' ? tries + 1 : 0);
  }, 20000);
}
/** Hero portrait of a match player (using /api/heroes data when available). */
const portrait = (p, opts) => heroPortrait(heroById.get(p.hero_id) || { id: p.hero_id, name: p.hero }, opts);
/** Image next to text that already names it: hidden from assistive tech. */
function decorative(node) { node.setAttribute('aria-hidden', 'true'); if (node.tagName === 'IMG') node.alt = ''; node.removeAttribute('aria-label'); node.removeAttribute('role'); return node; }
/** Table column with an in-cell bar scaled to the column maximum over `scale` (compact width for wide tables). */
function barCol(scale, c) {
  const max = Math.max(0, ...scale.map(r => r[c.key]).filter(v => typeof v === 'number' && isFinite(v)).map(Math.abs));
  return { ...c, render: r => {
    const v = r[c.key], txt = formatValue(v, c.fmt);
    if (typeof v !== 'number' || !isFinite(v) || !max) return txt;
    return el('span', { class: 'cell-bar compact' + (v < 0 ? ' neg' : '') },
      el('span', { class: 'cell-bar-track', 'aria-hidden': 'true' }, el('span', { class: 'cell-bar-fill', style: { width: Math.min(100, 100 * Math.abs(v) / max) + '%' } })),
      el('span', { class: 'cell-bar-val' }, txt));
  } };
}
const pname = p => p.name || `Account ${p.account_id}`;
const mvpOf = m => m.players.find(p => p.mvp_rank === 1) || null;
const teamSum = (m, t, k) => m.players.filter(p => p.team === t).reduce((a, p) => a + (p[k] || 0), 0);

function scoreboard(m, TN, verified) {
  const side = t => el('div', { class: `bside t${t}` + (m.winning_team === t ? ' won' : '') },
    el('div', { class: 'bstrip tilt-cards' }, m.players.filter(p => p.team === t).sort((x, y) => y.net_worth - x.net_worth).slice(0, 6)
      .map(p => el('span', { class: 'bcell', title: `${p.hero} · ${pname(p)}` }, portrait(p, { size: 'md', shape: 'card' })))),
    el('div', { class: 'blabel' },
      el('div', { class: 'bname' }, el('span', { class: `tag t${t}` }, `Team ${t}`), el('b', {}, TN[t])),
      el('div', { class: 'bmeta' }, `${fmt.int(teamSum(m, t, 'net_worth'))} gold · `, m.winning_team === t ? el('span', { class: 'sb-win' }, icon('trophy'), 'Victory') : el('span', { class: 'sb-lose' }, 'Defeat'))));
  return el('section', { class: 'panel scoreboard', 'aria-label': 'Scoreboard' },
    el('div', { class: 'sb-top' },
      el('h2', {}, `Match #${m.match_id}`),
      el('button', { type: 'button', class: 'danger small-btn', onclick: async () => { if (!confirm('Delete the saved match?')) return; try { await api.post(`/api/matches/${m.match_id}/delete`); location.hash = '#partidas'; } catch (e) { toast(e.message, true); } } }, 'Delete')),
    el('div', { class: 'hero-banner' }, side(0),
      el('div', { class: 'bcenter' },
        el('div', { class: 'sb-vs' }, 'KILLS · DURATION'),
        el('div', { class: 'bscore', 'aria-label': `${teamSum(m, 0, 'kills')} to ${teamSum(m, 1, 'kills')}` },
          el('span', { class: 't0' }, String(teamSum(m, 0, 'kills'))), ' : ', el('span', { class: 't1' }, String(teamSum(m, 1, 'kills')))),
        el('div', { class: 'sb-dur' }, fmt.mmss(m.duration_s)), el('div', { class: 'muted small' }, fmt.datetime(m.start_time))),
      side(1)),
    verified ? el('div', { class: 'muted small', style: { padding: '8px 16px' } }, verified.replace(/^ · /, '')) : null);
}

/** Gold difference (team 0 − team 1) with the key moments (objectives and Midboss). */
function goldPanel(m, tname) {
  const box = el('section', { class: 'panel gold' }, el('div', { class: 'section-head' }, el('h3', {}, 'Gold difference'),
    el('div', { class: 'legend' }, el('span', {}, el('i', { style: { background: 'var(--t0)' } }), `${tname(0)} ahead`), el('span', {}, el('i', { style: { background: 'var(--t1)' } }), `${tname(1)} ahead`))));
  const times = [...new Set(m.players.flatMap(p => (p.nw_timeline || []).map(x => x[0])))].sort((a, b) => a - b);
  if (times.length < 2) { box.append(el('p', { class: 'muted small' }, 'The match does not include the net worth timeline.')); return box; }
  const at = (p, t) => { const tl = p.nw_timeline || []; let v = 0; for (const [s, nw] of tl) { if (s <= t) v = nw; else break; } return v; };
  const pts = [[0, 0], ...times.map(t => [t, m.players.reduce((a, p) => a + (p.team === 0 ? 1 : -1) * at(p, t), 0)])];
  const W = 900, H = 200, pad = { l: 46, r: 10, t: 12, b: 34 };
  const T = Math.max(m.duration_s || 0, times[times.length - 1]);
  const maxAbs = Math.max(1000, ...pts.map(p => Math.abs(p[1])));
  const x = t => pad.l + (W - pad.l - pad.r) * t / T, y = v => pad.t + (H - pad.t - pad.b) * (1 - (v + maxAbs) / (2 * maxAbs));
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'goldchart'); svg.setAttribute('role', 'img');
  const final = pts[pts.length - 1][1];
  svg.setAttribute('aria-label', `Gold difference over the match; at the end ${fmt.signed0(final)} for ${final >= 0 ? tname(0) : tname(1)}`);
  const mk = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; svg.append(e); return e; };
  const line = pts.map(([t, v], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${line}L${x(pts[pts.length - 1][0])},${y(0)}L${x(0)},${y(0)}Z`;
  const clip = (id, y0, h) => { const d = mk('clipPath', { id }); const r = document.createElementNS(ns, 'rect'); r.setAttribute('x', 0); r.setAttribute('y', y0); r.setAttribute('width', W); r.setAttribute('height', h); d.append(r); };
  const uid = 'g' + m.match_id;
  clip(uid + 'a', 0, y(0)); clip(uid + 'b', y(0), H);
  for (const v of [maxAbs, maxAbs / 2, 0, -maxAbs / 2, -maxAbs]) {
    mk('line', { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: v === 0 ? 'zero' : 'gridl' });
    mk('text', { x: pad.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, v === 0 ? '0' : (v > 0 ? '+' : '−') + Math.round(Math.abs(v) / 1000) + 'k');
  }
  for (let mn = 0; mn * 60 <= T; mn += 5) mk('text', { x: x(mn * 60), y: H - 18, 'text-anchor': 'middle' }, mn + "'");
  mk('path', { d: area, class: 'area t0', 'clip-path': `url(#${uid}a)` });
  mk('path', { d: area, class: 'area t1', 'clip-path': `url(#${uid}b)` });
  mk('path', { d: line, class: 'gline' });
  // key moments on the bottom axis
  const ev = [
    ...m.objectives.filter(o => o.destroyed_s).map(o => ({ t: o.destroyed_s, team: o.destroyed_by, label: `${fmt.mmss(o.destroyed_s)} · ${tname(o.destroyed_by ?? (1 - o.owner_team))} destroys ${o.label}`, kind: o.type })),
    ...m.midboss.map(b => ({ t: b.t, team: b.team_claimed, label: `${fmt.mmss(b.t)} · Midboss: claimed by ${tname(b.team_claimed)}`, kind: 'Midboss' })),
  ];
  for (const e of ev) {
    const g = mk('g', { class: `moment t${e.team}` + (e.kind === 'Midboss' ? ' boss' : '') });
    const big = /Midboss|Patron|Core|Shrine|Titan/i.test(e.kind || '');
    const c = document.createElementNS(ns, big ? 'rect' : 'circle');
    if (big) { c.setAttribute('x', x(e.t) - 4.5); c.setAttribute('y', H - 9 - 4.5); c.setAttribute('width', 9); c.setAttribute('height', 9); c.setAttribute('transform', `rotate(45 ${x(e.t)} ${H - 9})`); }
    else { c.setAttribute('cx', x(e.t)); c.setAttribute('cy', H - 9); c.setAttribute('r', 3.5); }
    const tt = document.createElementNS(ns, 'title'); tt.textContent = e.label;
    g.append(c, tt);
    if (big) { const l = document.createElementNS(ns, 'line'); l.setAttribute('x1', x(e.t)); l.setAttribute('x2', x(e.t)); l.setAttribute('y1', pad.t); l.setAttribute('y2', H - pad.b); l.setAttribute('class', 'mline'); g.prepend(l); }
  }
  const peak0 = pts.reduce((a, p) => p[1] > a[1] ? p : a), peak1 = pts.reduce((a, p) => p[1] < a[1] ? p : a);
  box.append(el('div', { class: 'chart-scroll' }, svg),
    el('div', { class: 'gold-facts' },
      el('span', {}, 'Final: ', el('b', {}, fmt.signed0(final)), ` for ${final >= 0 ? tname(0) : tname(1)}`),
      el('span', {}, `Peak ${tname(0)}: `, el('b', {}, fmt.signed0(peak0[1])), ` (${fmt.mmss(peak0[0])})`),
      el('span', {}, `Peak ${tname(1)}: `, el('b', {}, fmt.signed0(-peak1[1])), ` (${fmt.mmss(peak1[0])})`),
      el('span', { class: 'muted' }, '● objective · ◆ Midboss/large structure (hover for details)')));
  return box;
}

/** Headline cards: MVP (only if the match provides mvp_rank), top damage, top farmer, most kills. Computed from the payload. */
function headlineCards(m, mvp, who, tname) {
  const best = (list, f) => list.reduce((a, p) => (f(p) > (a ? f(a) : -Infinity) ? p : a), null);
  const card = (title, p, value, unit, sub) => el('div', { class: 'stat-card' },
    el('div', { class: 'stat-card-visual' }, portrait(p, { size: 'md', shape: 'card' })),
    el('div', { class: 'stat-card-body' },
      el('div', { class: 'stat-card-title' }, title),
      el('div', { class: 'stat-card-value' }, el('b', {}, value), unit ? el('span', { class: 'stat-card-unit' }, ' ' + unit) : null),
      el('div', { class: 'stat-card-sub' }, el('b', {}, p.hero), ' · ', who(p)),
      el('div', { class: 'stat-card-foot' }, el('span', { class: `tag t${p.team}` }, tname(p.team)), sub ? el('span', { class: 'muted small' }, sub) : null)));
  const cards = [];
  if (mvp) cards.push(card('MVP', mvp, `${mvp.kills}/${mvp.deaths}/${mvp.assists}`, 'K/D/A', `${fmt.int(mvp.net_worth)} gold · as given by the match`));
  const dmg = best(m.players.filter(p => p.player_damage != null), p => p.player_damage);
  if (dmg) cards.push(card('Top hero damage', dmg, fmt.int(dmg.player_damage), 'damage', null));
  const stats = (m.player_stats || []).filter(r => r.troopers_per_min != null && r.jungla_per_min != null).map(r => ({ r, p: m.players.find(p => p.slot === r.slot) })).filter(x => x.p);
  const farm = stats.reduce((a, x) => (x.r.troopers_per_min + x.r.jungla_per_min > (a ? a.r.troopers_per_min + a.r.jungla_per_min : -Infinity) ? x : a), null);
  if (farm) cards.push(card('Top farmer', farm.p, fmt.dec(farm.r.troopers_per_min + farm.r.jungla_per_min, 1), 'troopers + jungle/min', `${fmt.dec(farm.r.troopers_per_min, 1)} troopers · ${fmt.dec(farm.r.jungla_per_min, 1)} jungle`));
  const kills = best(m.players, p => p.kills);
  if (kills) cards.push(card('Most kills', kills, String(kills.kills), 'kills', `${kills.kills}/${kills.deaths}/${kills.assists}`));
  return el('div', { class: 'stat-cards block', role: 'group', 'aria-label': 'Match highlights' }, cards);
}

function resumen(root, m, tname, ctx) {
  const mvp = mvpOf(m);
  const maxNW = Math.max(...m.players.map(p => p.net_worth || 0), 1);
  const maxKA = Math.max(...m.players.map(p => p.kills + p.deaths + p.assists), 1);
  const maxDmg = Math.max(...m.players.map(p => p.player_damage || 0), 1);
  const av = p => p.avatar ? el('img', { class: 'avatar-img', src: p.avatar, alt: '', loading: 'lazy', style: { width: '20px', height: '20px', marginRight: '6px', verticalAlign: 'middle' } }) : null;
  const who = p => p.player_id ? el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(p.player_id, ctx) }, av(p), pname(p)) : el('span', { class: 'muted' }, av(p), pname(p));
  root.append(headlineCards(m, mvp, who, tname));
  const grid = el('div', { class: 'grid2' });
  for (const t of [0, 1]) {
    const ps = m.players.filter(p => p.team === t).sort((a, b) => b.net_worth - a.net_worth);
    const k = teamSum(m, t, 'kills'), nw = teamSum(m, t, 'net_worth');
    grid.append(el('div', { class: `team-card t${t}` },
      el('h3', {}, el('span', { class: `tag t${t}` }, tname(t)), ` ${m.winning_team === t ? 'Victory' : 'Defeat'}`, el('span', { class: 'muted small' }, ` · ${k} kills · ${fmt.int(nw)} gold`)),
      el('ul', { class: 'plist' }, ps.map(p => el('li', { class: p === mvp ? 'is-mvp' : '' },
        el('div', { class: 'pl-who' }, portrait(p, { size: 'sm', shape: 'round' }), el('div', { class: 'pl-name' }, el('b', {}, p.hero), el('span', { class: 'small' }, who(p))), p === mvp ? el('span', { class: 'mvp-dot', title: 'MVP' }, icon('star')) : null),
        el('div', { class: 'pl-kda', title: `${p.kills} kills · ${p.deaths} deaths · ${p.assists} assists` },
          el('span', { class: 'kda-num' }, `${p.kills}/${p.deaths}/${p.assists}`),
          el('span', { class: 'kda-bar', 'aria-hidden': 'true', style: { width: (100 * (p.kills + p.deaths + p.assists) / maxKA) + '%' } },
            el('i', { class: 'k', style: { flex: p.kills } }), el('i', { class: 'd', style: { flex: p.deaths } }), el('i', { class: 'a', style: { flex: p.assists } }))),
        el('div', { class: 'pl-nw' }, el('span', { class: 'lbl' }, 'Gold'), el('span', { class: 'bar', 'aria-hidden': 'true' }, el('span', { style: { width: (100 * p.net_worth / maxNW) + '%' } })), el('span', { class: 'v' }, fmt.int(p.net_worth))),
        p.player_damage != null ? el('div', { class: 'pl-nw dmg' }, el('span', { class: 'lbl' }, 'Damage'), el('span', { class: 'bar', 'aria-hidden': 'true' }, el('span', { style: { width: (100 * p.player_damage / maxDmg) + '%' } })), el('span', { class: 'v' }, fmt.int(p.player_damage))) : null)))));
  }
  root.append(el('div', { class: 'legend' }, el('span', {}, el('i', { style: { background: 'var(--ok)' } }), 'kills'), el('span', {}, el('i', { style: { background: 'var(--bad)' } }), 'deaths'), el('span', {}, el('i', { style: { background: 'var(--muted)' } }), 'assists')), grid);
  const det = el('details', { class: 'block' }, el('summary', {}, 'Full table'));
  for (const t of [0, 1]) {
    det.append(el('h4', {}, tname(t)), dataTable([
      { key: 'hero', label: 'Hero', render: p => el('span', { class: 'hero-cell' }, portrait(p, { size: 'sm', shape: 'round' }), p.hero) },
      { key: 'name', label: 'Player', render: p => who(p) },
      { key: 'kills', label: 'K' }, { key: 'deaths', label: 'D' }, { key: 'assists', label: 'A' },
      barCol(m.players, { key: 'net_worth', label: 'Net worth', fmt: 'int' }), barCol(m.players, { key: 'player_damage', label: 'Damage', fmt: 'int' }), { key: 'last_hits', label: 'Last hits' }, { key: 'denies', label: 'Denies' }, { key: 'level', label: 'Level' },
      { key: 'comeback_gold_koth', label: 'Comeback Gold Koth' },
    ], m.players.filter(p => p.team === t), { sortKey: 'net_worth' }));
  }
  root.append(det);
}

function objetivos(root, m, tname) {
  root.append(el('p', { class: 'muted small' }, '“Team” is the OWNER of the objective; the opponent destroys it. If it did not fall, the first hit is shown. The ID mapping is inferred (editable in Settings).'));
  const cols = [
    { key: 'label', label: 'Objective', render: r => el('span', { class: 'obj-cell' }, decorative(objectiveImg(r.type, r.owner_team, { size: 'sm' })), r.label) }, { key: 'objective_id', label: 'ID' },
    { key: 'lane', label: 'Lane', render: r => r.lane ? laneChip(r.lane, m.lanes) : '' },
    { key: 'destroyed_s', label: 'Falls', fmt: 'mmss' },
    { key: 'first_damage_s', label: 'First hit', render: r => r.destroyed_s ? fmt.mmss(r.first_damage_s) : (r.first_damage_s ? `${fmt.mmss(r.first_damage_s)} (did not fall)` : 'no damage') },
    { key: 'player_damage', label: 'Player damage', fmt: 'int' }, { key: 'creep_damage', label: 'Trooper damage', fmt: 'int' },
  ];
  root.append(laneTracks(m, tname), kothCard(m, tname));
  const grid = el('div', { class: 'grid2' });
  for (const t of [0, 1]) {
    const rows = m.objectives.filter(o => o.owner_team === t);
    grid.append(el('div', {}, el('h3', {}, 'Objectives of ', el('span', { class: `tag t${t}` }, tname(t))), dataTable(cols, rows, { sortKey: 'destroyed_s', asc: true })));
  }
  root.append(el('div', { class: 'row' }, el('button', { onclick: () => csvDownload(`objectives_${m.match_id}.csv`, [
    { label: 'owner_team', csv: r => r.owner_team }, { label: 'objective', csv: r => r.label }, { label: 'id', csv: r => r.objective_id },
    { label: 'falls_s', csv: r => r.destroyed_s ?? '' }, { label: 'falls_mmss', csv: r => r.destroyed_s ? fmt.mmss(r.destroyed_s) : '' },
    { label: 'first_hit_s', csv: r => r.first_damage_s ?? '' }], m.objectives) }, 'Export CSV')), grid);
  const ev = side => m.objectives.filter(o => o.owner_team === side && o.destroyed_s).map(o => ({ t: o.destroyed_s, label: `${o.label} of ${tname(side)}`, side: side === 0 ? 't0' : 't1', kind: o.type }));
  const mb = m.midboss.map(x => ({ t: x.t, label: `Midboss: killed by ${tname(x.team_killed)}, claimed by ${tname(x.team_claimed)}`, side: x.team_killed === 0 ? 't0' : 't1', kind: 'Midboss' }));
  root.append(el('h3', { style: { marginTop: '14px' } }, 'Timeline'),
    el('p', { class: 'muted small' }, 'Colour = OWNER team of the objective that falls (filled amber = team 0, outlined blue = team 1).'),
    timeline({ rows: [
      { label: `${tname(0)} loses`, duration: m.duration_s, events: ev(0) },
      { label: `${tname(1)} loses`, duration: m.duration_s, events: ev(1) },
      { label: 'Midboss', duration: m.duration_s, events: mb },
    ] }));
}

/** One track per lane (+ “Base”) with each destroyed objective at its minute; border = owner team. */
function laneTracks(m, tname) {
  const fallen = m.objectives.filter(o => o.destroyed_s);
  const dur = Math.max(m.duration_s || 0, ...fallen.map(o => o.destroyed_s), 1);
  const laneIds = [...new Set([1, 3, 4, ...fallen.map(o => o.lane).filter(l => l != null)])];
  const GAP = 6, ROW_PX = 28; // min % between marks in one row; height of each mark row
  const row = (name, alias, color, list) => {
    const lastX = []; // last position (%) per row: nearby marks drop to another row
    const marks = list.slice().sort((a, b) => a.destroyed_s - b.destroyed_s).map(o => {
      const x = 100 * o.destroyed_s / dur;
      let r = lastX.findIndex(lx => x - lx >= GAP);
      if (r < 0) r = lastX.length;
      lastX[r] = x;
      return { o, x, r };
    });
    const rows = Math.max(1, lastX.length);
    return el('div', { class: 'lane-row', style: { '--lane': color } },
      el('div', { class: 'ln' }, name, alias ? el('small', {}, alias) : null),
      el('div', { class: 'lane-track', role: 'list', 'aria-label': `Objectives destroyed in ${name}`, style: { height: (6 + rows * ROW_PX) + 'px' } },
        marks.map(({ o, x, r }) => el('span', { class: `ev t${o.owner_team}`, role: 'listitem', style: { left: x.toFixed(2) + '%', top: (3 + ROW_PX * (r + 0.5)) + 'px' },
          title: `${o.type} of ${m.team_names[o.owner_team]} · ${fmt.mmss(o.destroyed_s)}` }, objectiveImg(o.type, o.owner_team, { size: 'sm' })))));
  };
  const axis = el('div', { class: 'lane-row lane-axis', 'aria-hidden': 'true' }, el('div'),
    el('div', { class: 'lane-track' }, Array.from({ length: Math.floor(dur / 600) + 1 }, (_, i) => el('span', { class: 'tick', style: { left: (100 * i * 600 / dur) + '%' } }, `${i * 10}'`))));
  return el('div', { class: 'lane-tracks' },
    el('h3', {}, 'Objectives by lane'),
    el('p', { class: 'muted small' }, 'Each mark is an objective destroyed at its minute; the border is the colour of the OWNER team (', el('span', { class: 'tag t0' }, tname(0)), el('span', { class: 'tag t1' }, tname(1)), ').'),
    laneIds.map(id => { const l = laneStyle(id, m.lanes); return row(l.nombre, l.alias, l.color, fallen.filter(o => o.lane === id)); }),
    row('Base', 'Shrines, Titan and Core', 'var(--muted)', fallen.filter(o => o.lane == null)),
    axis);
}

/** Demo state when there is no data: loading / no demo / not available (with its reason). */
function demoStatus(demo) {
  const st = demo?.state;
  if (st === 'pending') return el('div', { class: 'unavailable block', role: 'status' }, spinner('Loading demo data…'));
  if (st === 'nodemo') return el('div', { class: 'unavailable block' }, el('b', {}, 'Not available: '), 'this match has no demo.');
  return el('div', { class: 'unavailable block' }, el('b', {}, 'Not available: '), demo?.reason || 'there is no demo data for this match.');
}

const demoDone = m => m.demo?.state === 'done';
const teamTag = (t, tname) => t == null ? el('span', { class: 'muted' }, '–') : el('span', { class: `tag t${t}` }, tname(t));
/** Comeback at that moment: 0/1 = that team; -1 = none (not marked); null = no net worth samples. */
const comebackTag = (team, tname) => team === -1 ? null
  : team == null ? el('span', { class: 'tag comeback muted', title: 'No net worth samples to apply the 10% rule' }, 'comeback: —')
  : el('span', { class: `tag comeback t${team}`, title: '10% rule: net worth (interpolated) < 0.9 × the opponent’s' }, `comeback: ${tname(team)}`);

function kothCard(m, tname) {
  const d = demoDone(m) ? m.demo : null;
  const cb = (m.comeback && m.comeback.koth) || [];
  const rows = d ? (d.koth || []) : [];
  return el('div', { class: 'koth-card' },
    el('div', { class: 'koth-head' }, objectiveImg('KOTH', null, { size: 'lg' }), el('h3', {}, 'KOTH (Unstable Rift)')),
    d ? (rows.length ? el('ul', { class: 'koth-list cashins' }, rows.map((k, i) => el('li', {}, decorative(objectiveImg('KOTH', null, { size: 'sm' })),
      el('b', { class: 'ci-n' }, `#${k.n}`),
      el('span', {}, `start ${fmt.mmss(k.start_t)}`),
      k.completed_by == null ? el('span', { class: 'muted' }, 'not completed')
        : el('span', {}, 'completed ', fmt.mmss(k.completed_t), ' by ', teamTag(k.completed_by, tname)),
      comebackTag(cb[i], tname)))) : el('p', { class: 'muted small' }, 'There was no KOTH cash-in.')) : demoStatus(m.demo),
    el('div', { class: 'grid2' }, [0, 1].map(t => el('div', {},
      el('h4', {}, 'Comeback Gold Koth · ', el('span', { class: `tag t${t}` }, tname(t))),
      el('ul', { class: 'koth-list' }, m.players.filter(p => p.team === t).map(p =>
        el('li', {}, portrait(p, { size: 'sm', shape: 'round' }), el('span', {}, p.hero), el('b', {}, fmt.int(p.comeback_gold_koth || 0)))))))));
}

/** Rejuvenator icons, each in the colour of the team that takes it (from the demo's rejuv). */
function rejuvIcons(rejuv, tname) {
  const r0 = (rejuv && rejuv[0]) || 0, r1 = (rejuv && rejuv[1]) || 0;
  const owners = [...Array(r0).fill(0), ...Array(r1).fill(1)];
  const txt = owners.length ? [r0 ? `${r0} rejuvenators for ${tname(0)}` : null, r1 ? `${r1} rejuvenators for ${tname(1)}` : null].filter(Boolean).join(', ') : 'no rejuvenators';
  return el('span', { class: 'rejuvs', role: 'img', 'aria-label': txt, title: txt },
    owners.map(t => el('span', { class: `rj t${t}`, 'aria-hidden': 'true' }, objectiveImg('Rejuvenator', null, { size: 'sm' }))),
    el('span', { class: 'rj-txt' }, txt));
}

function dmgBar(damage, tname) {
  // no damage captured (Midboss seen only through the rejuvenators): missing data, not 0
  if (damage == null) return el('div', { class: 'dmg-duo' }, el('div', { class: 'small muted' }, 'Damage: not available'));
  const d0 = (damage && damage[0]) || 0, d1 = (damage && damage[1]) || 0, tot = d0 + d1;
  return el('div', { class: 'dmg-duo' },
    el('div', { class: 'dmg-bar', 'aria-hidden': 'true' },
      el('i', { class: 't0', style: { flex: tot ? d0 : 1 } }), el('i', { class: 't1', style: { flex: tot ? d1 : 1 } })),
    el('div', { class: 'small' }, `Damage: ${tname(0)} ${fmt.int(d0)} · ${tname(1)} ${fmt.int(d1)}`));
}

function midboss(root, m, tname) {
  root.append(el('div', { class: 'koth-head' }, objectiveImg('Midboss', null, { size: 'lg' }), el('h3', {}, 'Midboss')));
  if (!demoDone(m)) {
    root.append(demoStatus(m.demo),
      m.midboss.length ? dataTable([
        { key: 'n', label: '#', render: r => el('span', { class: 'obj-cell' }, decorative(objectiveImg('Midboss', null, { size: 'sm' })), String(r.n)) }, { key: 't', label: 'Minute', fmt: 'mmss' },
        { key: 'team_killed', label: 'Killed by', render: r => el('span', { class: `tag t${r.team_killed}` }, tname(r.team_killed)) },
        { key: 'team_claimed', label: 'Claimed by', render: r => el('span', { class: `tag t${r.team_claimed}` }, tname(r.team_claimed)) },
      ], m.midboss, { sortKey: 't', asc: true }) : el('p', { class: 'muted' }, 'There was no Midboss.'));
    return;
  }
  const evs = m.demo.midboss || [], cb = (m.comeback && m.comeback.midboss) || [];
  if (!evs.length) { root.append(el('p', { class: 'muted' }, 'There was no Midboss.')); return; }
  root.append(el('div', { class: 'mb-list' }, evs.map((e, i) => el('div', { class: 'mb-card' },
    el('div', { class: 'mb-head' }, decorative(objectiveImg('Midboss', null, { size: 'sm' })), el('b', {}, `Midboss #${e.n}`), el('span', {}, fmt.mmss(e.t)),
      el('span', {}, 'killed by ', teamTag(e.killer, tname)), comebackTag(cb[i], tname)),
    rejuvIcons(e.rejuv, tname),
    dmgBar(e.damage, tname),
    e.initiator != null ? el('div', { class: 'small' }, 'Started by ', teamTag(e.initiator, tname)) : null,
    e.stolen != null ? el('div', { class: 'small' }, 'Stolen: ', e.stolen ? 'yes' : 'no') : null))));
}

const LANE_UNAVAILABLE = 'Not available: the positions do not reveal each player’s lane.';
const srcLabel = lp => lp?.source === 'demo' ? 'demo' : lp?.source === 'aprox' ? 'approx., no demo' : 'no data';
const srcNote = lp => el('p', { class: 'muted small' }, 'Source: ', el('b', {}, srcLabel(lp)),
  lp?.source === 'aprox' && lp?.demo_incompleto ? ' · this match’s demo is incomplete (pauses leave out part of the first 10 minutes), so it is not used.' : '',
  lp?.source === 'aprox' ? ' · the damage split (lane/gank) and the ganks need the demo (“–”); the rest is approximated from the match stats.' : '');
const minOf = t => t == null ? null : fmt.mmss(t);

/** Two bars (dealt / taken) on a common scale. */
function dmgPair(done, taken, max) {
  const bar = (v, cls, lbl) => el('div', { class: 'lp-bar' }, el('span', { class: 'lbl' }, lbl),
    el('span', { class: 'bar', 'aria-hidden': 'true' }, el('span', { class: cls, style: { width: (v == null ? 0 : 100 * v / max) + '%' } })),
    el('span', { class: 'v' }, v == null ? '–' : fmt.int(v)));
  return el('div', { class: 'lp-bars' }, bar(done, 'done', 'Dealt'), bar(taken, 'taken', 'Taken'));
}

function faseLineas(root, m, tname) {
  const lp = m.lane_phase;
  if (!lp) { root.append(el('div', { class: 'unavailable block' }, el('b', {}, 'Not available: '), 'the laning phase of this match could not be computed.')); return; }
  root.append(srcNote(lp));
  if (!lp.valid) { root.append(el('div', { class: 'unavailable block' }, LANE_UNAVAILABLE)); return; }
  const byslot = new Map(m.players.map(p => [p.slot, p]));
  const hname = s => byslot.get(s)?.hero || `#${s}`;
  const laneIds = Object.keys(lp.lanes).map(Number).sort((a, b) => a - b);
  const all = laneIds.flatMap(l => Object.values(lp.lanes[String(l)]));
  const max = Math.max(1, ...all.flatMap(c => [c.dmg_done || 0, c.dmg_taken || 0]));
  const heroBit = s => { const p = byslot.get(s); return p ? el('span', { class: 'hero-cell' }, portrait(p, { size: 'sm', shape: 'round' }), el('b', {}, p.hero)) : el('b', {}, hname(s)); };
  const gank = g => {
    if (lp.source !== 'demo') return el('span', { class: 'muted' }, '–');  // ganks need the demo
    if (!g) return el('span', { class: 'muted' }, 'none');
    return el('span', { class: 'gank-line' }, `${minOf(g.t)} · `, heroBit(g.attacker_slot), ' ganks ', heroBit(g.victim_slot), g.kind === 'kill' ? ' (kill)' : ' (damage)');
  };
  const num = v => v == null ? el('span', { class: 'muted' }, '–') : el('b', {}, fmt.int(v));
  const guard = t => t == null ? el('span', { class: 'muted' }, 'did not fall') : el('b', {}, minOf(t));
  const card = (lane, t) => {
    const c = lp.lanes[String(lane)][String(t)];
    if (!c) return el('div', { class: `team-card t${t}` }, el('h4', {}, el('span', { class: `tag t${t}` }, tname(t))), el('p', { class: 'muted small' }, 'No data.'));
    return el('div', { class: `team-card t${t} lp-card` },
      el('h4', {}, el('span', { class: `tag t${t}` }, tname(t))),
      el('div', { class: 'lp-duo' }, (c.slots || []).map(sl => { const p = byslot.get(sl); return p ? el('span', { class: 'lp-hero' }, portrait(p, { size: 'sm', shape: 'round' }), el('span', {}, p.hero)) : null; })),
      dmgPair(c.dmg_done, c.dmg_taken, max),
      el('dl', { class: 'lp-facts' },
        el('dt', {}, 'Damage dealt in lane'), el('dd', {}, num(c.dmg_done_lane)),
        el('dt', {}, 'Damage taken in lane'), el('dd', {}, num(c.dmg_taken_lane)),
        el('dt', {}, 'Damage taken from ganks'), el('dd', {}, num(c.dmg_taken_gank)),
        el('dt', {}, 'Enemy Guardian taken down'), el('dd', {}, guard(c.guardian_taken_t)),
        el('dt', {}, 'Own Guardian lost'), el('dd', {}, guard(c.guardian_lost_t)),
        el('dt', {}, 'Kills / deaths'), el('dd', {}, el('b', {}, `${c.kills ?? '–'} / ${c.deaths ?? '–'}`)),
        el('dt', { style: { gridColumn: '1 / -1' } }, 'First gank made'), el('dd', { class: 'wide' }, gank(c.first_gank_made)),
        el('dt', { style: { gridColumn: '1 / -1' } }, 'First gank suffered'), el('dd', { class: 'wide' }, gank(c.first_gank_suffered))));
  };
  for (const l of laneIds) root.append(el('section', { class: 'lp-lane' }, el('h3', {}, laneChip(l, m.lanes)), el('div', { class: 'grid2' }, card(l, 0), card(l, 1))));
  root.append(el('p', { class: 'muted small' }, 'Lanes are assigned by each player’s position, not by map side. “–” = no data.'));
}

function jugadores(root, m, tname) {
  const ps = m.player_stats, lp = m.lane_phase;
  if (!ps || !ps.length) { root.append(el('div', { class: 'unavailable block' }, el('b', {}, 'Not available: '), 'the per-player breakdown of this match could not be computed.')); return; }
  const byslot = new Map(m.players.map(p => [p.slot, p]));
  const rows = ps.map(r => ({ ...r, pl: byslot.get(r.slot), hero: byslot.get(r.slot)?.hero || `#${r.slot}`, pname: byslot.get(r.slot) ? pname(byslot.get(r.slot)) : '' }));
  const detail = el('div', { class: 'pj-detail' });
  let sel = null;
  root.append(srcNote(lp), el('p', { class: 'muted small' }, 'Pick a player (click their row or use the selector) to see where they killed and died, and their souls by source.'));
  const laneCell = r => r.lane == null ? el('span', { class: 'muted' }, '–') : laneChip(r.lane, m.lanes);
  const cols = [
    { key: 'hero', label: 'Hero', render: r => el('span', { class: 'hero-cell' }, r.pl ? portrait(r.pl, { size: 'sm', shape: 'round' }) : null, r.hero) },
    { key: 'pname', label: 'Player' },
    { key: 'team', label: 'Team', render: r => teamTag(r.team, tname) },
    { key: 'lane', label: 'Lane', render: laneCell, sort: r => r.lane ?? 99 },
    { key: 'kda', label: 'KDA', render: r => [r.kills, r.deaths, r.assists].map(v => v ?? '–').join('/') + (r.kda != null ? ` (${fmt.dec(r.kda, 1)})` : ''), sort: r => r.kda ?? -1 },
    barCol(rows, { key: 'troopers_per_min', label: 'Troopers/min', fmt: '1' }), barCol(rows, { key: 'jungla_per_min', label: 'Jungle/min', fmt: '1' }),
    barCol(rows, { key: 'nw_per_min', label: 'NW/min', fmt: 'int' }), barCol(rows, { key: 'nw_at_600', label: "NW at 10'", fmt: 'int' }),
    barCol(rows, { key: 'player_damage', label: 'Damage', fmt: 'int' }),
    barCol(rows, { key: 'lane_dmg_done', label: 'Lane damage dealt', fmt: 'int' }), barCol(rows, { key: 'lane_dmg_taken', label: 'Lane damage taken', fmt: 'int' }),
    { key: 'ganks_made', label: 'Ganks made', fmt: 'int' }, { key: 'ganks_suffered', label: 'Ganks suffered', fmt: 'int' },
  ];
  const picker = el('select', { 'aria-label': 'Player' }, el('option', { value: '' }, 'Pick a player…'),
    rows.map(r => el('option', { value: String(r.slot) }, `${r.hero} · ${r.pname || '—'} (${tname(r.team)})`)));
  picker.addEventListener('change', () => { sel = picker.value === '' ? null : rows.find(r => String(r.slot) === picker.value); showPlayer(); });
  root.append(el('div', { class: 'row' }, picker), dataTable(cols, rows, { sortKey: 'team', asc: true, onRowClick: r => { sel = r; picker.value = String(r.slot); showPlayer(); } }), detail);

  function cellMap(title, cells, team, color, absent) {
    const G = 8;
    if (cells == null) return el('div', { class: 'pj-map' }, el('h4', {}, title), el('p', { class: 'muted small' }, absent));
    const box = el('div');
    const map = new MapView(box, { size: 380, grid: G, label: title });
    // team 1: the cells come rotated (own base at the bottom); the rotation is undone and the whole map is rotated
    const cs = team === 1 ? cells.map(([c, r, n]) => [G - 1 - c, G - 1 - r, n]) : cells;
    map.ready.then(() => map.setLayers(cs.length ? [{ kind: 'cells', cells: cs, color, labels: true }] : [], { rotate: team === 1, grid: G }));
    return el('div', { class: 'pj-map' }, el('h4', {}, `${title} (${cells.reduce((a, c) => a + c[2], 0)})`), box,
      cells.length ? null : el('p', { class: 'muted small' }, 'None with a position.'));
  }
  function showPlayer() {
    detail.innerHTML = '';
    if (!sel) return;
    const color = sel.team === 1 ? COLORS.t1 : COLORS.t0;
    const names = m.economy?.source_names || {};
    const src = sel.sources;
    detail.append(el('h3', {}, sel.pl ? portrait(sel.pl, { size: 'sm', shape: 'round' }) : null, ` ${sel.hero} · ${sel.pname || '—'} `, laneCell(sel)),
      el('p', { class: 'muted small' }, 'Maps with the player’s own base at the bottom. Kills = where the opponent died; deaths = where the player died.'),
      el('div', { class: 'grid2' }, cellMap('Kills', sel.kill_cells || [], sel.team, color), cellMap('Deaths', sel.death_cells || [], sel.team, color)),
      el('h4', {}, 'Without Midboss and KOTH fights'),
      el('p', { class: 'muted small' }, sel.fights
        ? `Counts by fight type (kills / deaths): midboss ${sel.fights.kills.midboss} / ${sel.fights.deaths.midboss}, KOTH ${sel.fights.kills.koth} / ${sel.fights.deaths.koth}, rest ${sel.fights.kills.rest} / ${sel.fights.deaths.rest}, no position ${sel.fights.kills.unknown} / ${sel.fights.deaths.unknown}. Events without a position are left off the maps.`
        : 'Not available: the KOTH cannot be identified without the match demo.'),
      el('div', { class: 'grid2' },
        cellMap('Kills without objective fights', sel.kill_cells_rest, sel.team, color, 'Not available without the demo (KOTH not identifiable).'),
        cellMap('Deaths without objective fights', sel.death_cells_rest, sel.team, color, 'Not available without the demo (KOTH not identifiable).')),
      el('h4', {}, 'Souls by source'),
      src && Object.keys(src).length ? dataTable([{ key: 'src', label: 'Source' }, { key: 'v', label: 'Souls', fmt: 'int' }],
        Object.entries(src).map(([k, v]) => ({ src: names[k] || `Source ${k}`, v })), { sortKey: 'v' })
        : el('p', { class: 'muted small' }, 'Not available: the match has no souls-by-source data for this player.'));
  }
}

const ECO_COLS = [['troopers_kills', 'Troopers/min'], ['jungla_kills', 'Jungle/min'], ['net_worth', 'Net worth/min']];

function economia(root, m, tname) {
  const eco = m.economy;
  if (!eco || !eco.players || !eco.players.length) { root.append(el('p', { class: 'muted' }, 'Not available: the match has no economy data.')); return; }
  const names = eco.source_names || {};
  const sids = Object.keys(names).filter(id => eco.players.some(p => (p.sources || {})[id]));
  const byslot = new Map(m.players.map(p => [p.slot, p]));
  root.append(el('p', { class: 'muted small' }, 'Souls earned by source (match total) and per-minute rates. “–” = no data.'));
  const ecoRows = eco.players.map(p => {
    const r = { pl: byslot.get(p.slot), slot: p.slot, team: p.team, hero: byslot.get(p.slot)?.hero || `#${p.slot}` };
    for (const id of sids) r['s' + id] = (p.sources || {})[id] ?? 0;
    for (const [k] of ECO_COLS) r['r_' + k] = (p.per_min || {})[k] ?? null;
    return r;
  });
  for (const t of [0, 1]) {
    const rows = ecoRows.filter(r => r.team === t);
    // bars share one scale per column across both teams so they can be compared
    const cols = [
      { key: 'hero', label: 'Hero', render: r => r.pl ? el('span', { class: 'hero-cell' }, portrait(r.pl, { size: 'sm', shape: 'round' }), r.pl.hero) : r.hero },
      ...sids.map(id => barCol(ecoRows, { key: 's' + id, label: names[id], fmt: 'int' })),
      ...ECO_COLS.map(([k, l]) => barCol(ecoRows, { key: 'r_' + k, label: l, fmt: '1' })),
    ];
    root.append(el('h4', {}, tname(t)), dataTable(cols, rows, { sortKey: 'r_net_worth' }));
  }
  const labels = ['0–10 min', '10–20 min', '20 min–end'];
  const trows = [];
  for (const [k, l] of ECO_COLS) for (const t of [0, 1]) {
    const ph = (eco.teams[String(t)] || {}).per_phase || [];
    const r = { metric: `${l} · ${tname(t)}` };
    labels.forEach((_, i) => { r['p' + i] = ph[i] ? (ph[i][k] ?? null) : null; });
    trows.push(r);
  }
  root.append(el('h4', {}, 'Rates by team and phase'),
    dataTable([{ key: 'metric', label: 'Metric' }, ...labels.map((l, i) => ({ key: 'p' + i, label: l, fmt: '1' }))], trows, {}));
}

async function minimapa(root, m, tname) {
  const status = el('div', {}, spinner('Decoding positions…'));
  root.append(status);
  let pos, info;
  try { [pos, info] = await Promise.all([api.get(`/api/matches/${m.match_id}/positions?step=2`), loadMapInfo()]); }
  catch (e) { status.replaceWith(errorBox(e.message, () => { root.innerHTML = ''; minimapa(root, m, tname); }, 'Could not load the positions')); return; }
  status.remove();
  const dur = m.duration_s, step = pos.interval_s;
  const st = { team: 'all', slot: 'all', from: 0, to: Math.ceil(dur / 60), heat: true, deaths: true, noObj: false, lanes: true, objImgs: false, koth: false, objectives: false, rotate: false };
  const teamSel = el('select', { 'aria-label': 'Team' }, [['all', 'Both teams'], ['0', tname(0)], ['1', tname(1)]].map(([v, l]) => el('option', { value: v }, l)));
  const slotSel = el('select', { 'aria-label': 'Player' }, el('option', { value: 'all' }, 'All players'),
    m.players.map(p => el('option', { value: p.slot }, `${p.hero} · ${pname(p)} (${tname(p.team)})`)));
  const from = el('input', { 'aria-label': 'From minute', type: 'number', min: 0, max: st.to, value: 0, style: { width: '64px' } });
  const to = el('input', { 'aria-label': 'To minute', type: 'number', min: 0, max: st.to, value: st.to, style: { width: '64px' } });
  const chk = (key, label) => { const c = el('input', { type: 'checkbox', checked: st[key] }); c.addEventListener('change', () => { st[key] = c.checked; draw(); }); return el('label', {}, c, label); };
  const noObjBox = el('input', { type: 'checkbox' });
  noObjBox.addEventListener('change', () => { st.noObj = noObjBox.checked; draw(); });
  const chkNoObj = el('label', {}, noObjBox, 'Exclude objective fights');
  const box = el('div');
  const map = new MapView(box, { size: 820, label: `Minimap of match ${m.match_id}` });
  const counts = el('div', { class: 'muted small' });
  root.append(el('div', { class: 'row' }, teamSel, slotSel, el('label', {}, 'minute', from, '–', to), chk('heat', 'position heat'), chk('deaths', 'deaths ✕'), chkNoObj,
    chk('lanes', 'lanes'), chk('objImgs', 'objectives'), chk('koth', 'KOTH'), chk('objectives', 'objective codes'), chk('rotate', 'rotate 180°'), el('button', { onclick: () => map.exportPNG(`minimap_${m.match_id}.png`) }, 'Export PNG')),
    legend([[COLORS.t0, tname(0)], [COLORS.t1, tname(1)], [COLORS.neutral, 'death (colour = victim’s team)', 'x']]), counts, box,
    el('p', { class: 'muted small' }, `Calibration: ${info.calibration?.source || '—'}. Positions with 0 health (dead) are discarded.`));
  for (const [i, k] of [[teamSel, 'team'], [slotSel, 'slot']]) i.addEventListener('change', () => { st[k] = i.value; draw(); });
  for (const [i, k] of [[from, 'from'], [to, 'to']]) i.addEventListener('input', () => { st[k] = +i.value; draw(); });

  function relToWorld(u, v) {
    const c = info.calibration;
    if (c.invert_x) u = 1 - u; if (c.invert_y !== false) v = 1 - v;
    return [c.x_min + u * (c.x_max - c.x_min), c.y_min + v * (c.y_max - c.y_min)];
  }
  function draw() {
    const t0 = st.from * 60, t1 = st.to * 60;
    const keep = p => (st.team === 'all' || String(p.team) === st.team) && (st.slot === 'all' || String(p.slot) === st.slot);
    const layers = [];
    let n = 0;
    if (st.lanes) for (const lp of info.lane_paths || []) layers.push({ kind: 'paths', paths: [lp.points], color: lp.color, width: 4, alpha: 0.55 });
    if (st.heat) for (const team of [0, 1]) {
      const pts = [];
      for (const p of pos.players.filter(p => p.team === team && keep(p))) {
        for (let i = Math.floor(t0 / step); i < Math.min(p.x.length, t1 / step); i++) if (p.x[i] != null) pts.push([p.x[i], p.y[i]]);
      }
      n += pts.length;
      layers.push({ kind: 'heat', points: pts, color: team ? COLORS.t1 : COLORS.t0, radius: 12 });
    }
    // “without objective fights” can only be computed with the demo (otherwise the KOTH cannot be identified)
    const fx = m.fights, labels = fx?.koth_known && fx.labels?.length === m.deaths.length ? fx.labels : null;
    noObjBox.disabled = !labels;
    noObjBox.title = labels ? '' : 'Needs the match demo: the KOTH cannot be identified without it.';
    if (!labels) { noObjBox.checked = false; st.noObj = false; }
    const noObj = st.noObj && labels;
    const nAll = m.deaths.filter(d => d.t >= t0 && d.t <= t1 && keep({ team: d.victim_team, slot: d.victim_slot }) && d.x != null).length;
    const deaths = m.deaths.filter((d, i) => d.t >= t0 && d.t <= t1 && keep({ team: d.victim_team, slot: d.victim_slot }) && d.x != null && (!noObj || labels[i] === 'rest'));
    if (st.deaths) layers.push({ kind: 'crosses', points: deaths.map(d => [d.x, d.y, 0, 0, d.victim_team ? COLORS.t1 : COLORS.t0]) });
    if (st.objImgs && info.objective_positions) {
      const items = [];
      for (const [k, v] of Object.entries(info.objective_positions)) {
        const type = /tier1/.test(k) ? 'Guardian' : /tier2/.test(k) ? 'Walker' : /titan|core/.test(k) ? 'Titan' : null;
        if (!type) continue;
        const [x, y] = relToWorld(v.left_relative, v.top_relative);
        const color = k.startsWith('team0') ? COLORS.t0 : COLORS.t1;
        items.push({ x, y, src: objectiveSrc(type), size: type === 'Guardian' ? 30 : 26, shape: type === 'Guardian' ? 'diamond' : undefined, color, label: color });
      }
      layers.push({ kind: 'images', items });
    }
    if (st.koth && info.koth?.length) layers.push({ kind: 'images', items: info.koth.map(([x, y]) => ({ x, y, src: objectiveSrc('KOTH'), size: 30, label: COLORS.neutral })) });
    if (st.objectives && info.objective_positions) {
      layers.push({ kind: 'markers', points: Object.entries(info.objective_positions).map(([k, v]) => {
        const [x, y] = relToWorld(v.left_relative, v.top_relative);
        return [x, y, k.replace(/^team\d_/, '').replace('tier1_', 'G').replace('tier2_', 'W'), k.startsWith('team0') ? COLORS.t0 : COLORS.t1];
      }) });
    }
    counts.textContent = `${n} positions (every ${step} s) · ${deaths.length} deaths in range`
      + (noObj ? ` (excluded ${nAll - deaths.length} in Midboss/KOTH fights)` : '')
      + (!labels ? ' · "Exclude objective fights" needs the match demo' : '');
    map.setLayers(layers, { rotate: st.rotate });
  }
  await map.ready;
  draw();
}

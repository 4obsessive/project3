// Hash router + update status bar.
import { api, invalidatePlayers } from './api.js';
import { el, fmt, toast, errorBox } from './util.js';
import { skeleton, windowText } from './ui.js';
import { initSearch } from './search.js';
import { closeDrawer } from './views/profile.js';
import { icon } from './icons.js';

const VIEWS = {
  home: () => import('./views/home.js'),
  players: () => import('./views/players.js'),
  hero: () => import('./views/hero.js'),
  climbers: () => import('./views/climbers.js'),
  teams: () => import('./views/teams.js'),
  matches: () => import('./views/matches.js'),
  report: () => import('./views/report.js'),
  settings: () => import('./views/settings.js'),
};

// old Spanish hash routes keep working
const LEGACY_ROUTES = { inicio: 'home', jugadores: 'players', heroe: 'hero', equipos: 'teams', informe: 'report', partidas: 'matches', ajustes: 'settings' }; /* es-ok */

const GROUP = { home: 'Scouting', players: 'Scouting', hero: 'Scouting', climbers: 'Scouting', teams: 'Teams', report: 'Teams', matches: 'Analysis', settings: 'System' };
const SKELETON = { home: 'tiles', players: 'table', hero: 'grid', climbers: 'table', teams: 'grid', matches: 'table', report: 'table', settings: 'table' };

// title and subtitle of each view
export const META = {
  home: { title: 'Home', sub: 'Scouting overview: the top players by reliable score, who is climbing, standout free agents and the most played heroes.' },
  players: { title: 'Players', sub: 'Every tracked player: compare last-month performance, filter free agents and open their profile.' },
  hero: { title: 'By hero', sub: 'Pick a hero and see who plays it best right now.' },
  climbers: { title: 'Climbers', sub: 'Who is climbing the leaderboard fastest and who just entered.' },
  teams: { title: 'Teams', sub: 'Rosters from equipos.txt with the performance of each player and a link to their report.' },
  matches: { title: 'Matches', sub: 'Load a match by ID or JSON and review it: scoreboard, gold, objectives and minimap.' },
  report: { title: 'Team report', sub: 'Aggregated team stats from their latest matches, ready to print.' },
  settings: { title: 'Settings', sub: 'Region, automatic updates, hero roles, objectives and minimap calibration.' },
};
for (const a of document.querySelectorAll('#nav a')) {
  const label = a.textContent;
  a.textContent = '';
  a.append(icon(a.dataset.view), el('span', { class: 'nav-label' }, label));
}

const ctx = { status: null, teamNames: { 0: 'Hidden King', 1: 'Archmother' }, params: [], query: {} };
let lastSuccess = null, renderSeq = 0;

async function route() {
  const raw = location.hash.slice(1) || 'home';
  const [pathPart, qs] = raw.split('?');
  const [name0, ...params] = pathPart.split('/');
  const name = LEGACY_ROUTES[name0] || name0;
  if (name !== name0) { // legacy Spanish hash: rewrite it so the rest of the app sees the English name
    history.replaceState(null, '', '#' + name + (params.length ? '/' + params.join('/') : '') + (qs ? '?' + qs : ''));
  }
  const view = VIEWS[name] ? name : 'home';
  ctx.params = params.map(decodeURIComponent);
  ctx.query = Object.fromEntries(new URLSearchParams(qs || ''));
  document.querySelectorAll('#nav a').forEach(a => {
    const on = a.dataset.view === view;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  const root = document.getElementById('view');
  closeDrawer(false);
  const seq = ++renderSeq;
  root.innerHTML = '';
  root.setAttribute('aria-busy', 'true');
  // spinner de cambio de ruta (la vista lo sustituye al pintar)
  const loading = skeleton(SKELETON[view] || 'table');
  root.append(loading);
  const meta0 = META[view];
  document.getElementById('crumb').replaceChildren(el('span', {}, GROUP[view] + ' / '), el('b', {}, meta0.title));
  document.title = `${meta0.title} · Deadlock Scouting`;
  try {
    const mod = await VIEWS[view]();
    if (seq !== renderSeq) return;
    // la vista se pinta oculta y aparece al terminar su primera carga
    const content = el('div', { hidden: true });
    const meta = META[view];
    if (meta?.sub) root.append(el('header', { class: 'page-head' },
      el('div', {}, el('h1', {}, meta.title), el('p', {}, meta.sub))));
    root.append(content);
    await mod.render(content, ctx);
    if (seq !== renderSeq) return;
    content.hidden = false;
  } catch (e) {
    console.error(e);
    if (seq !== renderSeq) return;
    root.innerHTML = '';
    root.append(errorBox(e.message, route));
    loading.remove();
  } finally {
    if (seq === renderSeq) { loading.remove(); root.removeAttribute('aria-busy'); }
  }
}
ctx.onPlayersChanged = () => { if ((location.hash || '#players').startsWith('#players')) route(); };

function renderStatus(box, s, compact) {
  box.innerHTML = '';
  const line = el('div', { class: 'status-line' });
  if (s.running) {
    const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
    line.append(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { class: 'status-text', title: `${s.label || ''} ${s.message || ''}` }, `${s.label || 'Updating'}${s.message ? ' · ' + s.message : ''}`));
    box.append(line, el('div', { class: 'progress', title: `${s.done}/${s.total}` }, el('div', { style: { width: pct + '%' } })));
  } else {
    const state = s.error ? 'bad' : s.last_success ? 'ok' : 'idle';
    const text = s.last_success ? `Updated ${fmt.ago(s.last_success)}` : 'Not updated yet';
    line.append(el('span', { class: `dot ${state}`, 'aria-hidden': 'true' }),
      el('span', { class: 'status-text', title: s.error || (s.next_run ? `Next: ${fmt.datetime(s.next_run)}` : null) },
        s.error ? 'Last update failed (will resume)' : text));
    box.append(line);
  }
  box.append(el('button', { type: 'button', class: 'ghost', disabled: s.running, title: 'Update now', 'aria-label': compact ? 'Update now' : null, onclick: async () => { try { const r = await api.post('/api/update'); toast(r.message); pollStatus(); } catch (e) { toast(e.message, true); } } },
    icon('refresh'), el('span', { class: 'btn-label' }, 'Update')));
}

async function pollStatus() {
  let s;
  try { s = await api.get('/api/status'); } catch { setTimeout(pollStatus, 10000); return; }
  ctx.status = s;
  renderStatus(document.getElementById('status'), s, false);
  renderStatus(document.getElementById('status-mobile'), s, true);
  const chip = document.getElementById('window-chip');
  const wt = windowText(s.stats_window);
  chip.hidden = !wt;
  chip.replaceChildren(el('span', { class: 'dot-live', 'aria-hidden': 'true' }), wt);
  chip.title = 'Stats window and mode (recomputed on every update)';
  // cuando termina una actualización, refrescar los datos de la vista actual
  if (lastSuccess !== null && s.last_success && s.last_success !== lastSuccess) {
    invalidatePlayers();
    toast('Data updated');
    const v = (location.hash.slice(1) || 'home').split(/[/?]/)[0];
    if (['home', 'players', 'hero', 'climbers', 'teams', ''].includes(v)) route();
  }
  lastSuccess = s.last_success || 0;
  setTimeout(pollStatus, s.running ? 2000 : 20000);
}

window.addEventListener('hashchange', route);
initSearch(document.getElementById('gsearch'), ctx);
pollStatus().then(route);

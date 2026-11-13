// Router por hash + barra de estado de la actualización.
import { api, invalidatePlayers } from './api.js';
import { el, fmt, toast, errorBox } from './util.js';
import { skeleton, windowText } from './ui.js';
import { initSearch } from './search.js';
import { closeDrawer } from './views/profile.js';
import { icon } from './icons.js';

const VIEWS = {
  inicio: () => import('./views/home.js'),
  jugadores: () => import('./views/players.js'),
  heroe: () => import('./views/hero.js'),
  climbers: () => import('./views/climbers.js'),
  equipos: () => import('./views/teams.js'),
  partidas: () => import('./views/matches.js'),
  informe: () => import('./views/report.js'),
  ajustes: () => import('./views/settings.js'),
};

const GROUP = { inicio: 'Scouting', jugadores: 'Scouting', heroe: 'Scouting', climbers: 'Scouting', equipos: 'Equipos', informe: 'Equipos', partidas: 'Análisis', ajustes: 'Sistema' };
const SKELETON = { inicio: 'tiles', jugadores: 'table', heroe: 'grid', climbers: 'table', equipos: 'grid', partidas: 'table', informe: 'table', ajustes: 'table' };

// título, subtítulo (para qué sirve la sección) e icono de cada vista
export const META = {
  inicio: { title: 'Inicio', sub: 'Resumen del scouting: los mejores por score fiable, quién sube, libres destacados y héroes más jugados.' },
  jugadores: { title: 'Jugadores', sub: 'Todos los jugadores seguidos: compara su rendimiento del último mes, filtra libres y abre su perfil.' },
  heroe: { title: 'Por héroe', sub: 'Elige un héroe y descubre quién lo juega mejor ahora mismo.' },
  climbers: { title: 'Climbers', sub: 'Quién sube más rápido en la leaderboard y quién acaba de entrar.' },
  equipos: { title: 'Equipos', sub: 'Plantillas de equipos.txt con el rendimiento de cada jugador y acceso a su informe.' },
  partidas: { title: 'Partidas', sub: 'Carga una partida por ID o JSON y revísala: marcador, oro, objetivos y minimapa.' },
  informe: { title: 'Informe de equipo', sub: 'Estadísticas agregadas de un equipo a partir de sus últimas partidas, listas para imprimir.' },
  ajustes: { title: 'Ajustes', sub: 'Región, actualización automática, roles por héroe, objetivos y calibración del minimapa.' },
};
for (const a of document.querySelectorAll('#nav a')) {
  const label = a.textContent;
  a.textContent = '';
  a.append(icon(a.dataset.view), el('span', { class: 'nav-label' }, label));
}

const ctx = { status: null, teamNames: { 0: 'Hidden King', 1: 'Archmother' }, params: [], query: {} };
let lastSuccess = null, renderSeq = 0;

async function route() {
  const raw = location.hash.slice(1) || 'inicio';
  const [pathPart, qs] = raw.split('?');
  const [name, ...params] = pathPart.split('/');
  const view = VIEWS[name] ? name : 'inicio';
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
ctx.onPlayersChanged = () => { if ((location.hash || '#jugadores').startsWith('#jugadores')) route(); };

function renderStatus(box, s, compact) {
  box.innerHTML = '';
  const line = el('div', { class: 'status-line' });
  if (s.running) {
    const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
    line.append(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { class: 'status-text', title: `${s.label || ''} ${s.message || ''}` }, `${s.label || 'Actualizando'}${s.message ? ' · ' + s.message : ''}`));
    box.append(line, el('div', { class: 'progress', title: `${s.done}/${s.total}` }, el('div', { style: { width: pct + '%' } })));
  } else {
    const state = s.error ? 'bad' : s.last_success ? 'ok' : 'idle';
    const text = s.last_success ? `Actualizado ${fmt.ago(s.last_success)}` : 'Sin actualizar todavía';
    line.append(el('span', { class: `dot ${state}`, 'aria-hidden': 'true' }),
      el('span', { class: 'status-text', title: s.error || (s.next_run ? `Próxima: ${fmt.datetime(s.next_run)}` : null) },
        s.error ? 'Error en la última actualización (se reanudará)' : text));
    box.append(line);
  }
  box.append(el('button', { type: 'button', class: 'ghost', disabled: s.running, title: 'Actualizar ahora', 'aria-label': compact ? 'Actualizar ahora' : null, onclick: async () => { try { const r = await api.post('/api/update'); toast(r.message); pollStatus(); } catch (e) { toast(e.message, true); } } },
    icon('refresh'), el('span', { class: 'btn-label' }, 'Actualizar')));
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
  chip.title = 'Ventana y modo de las stats (se recalcula en cada actualización)';
  // cuando termina una actualización, refrescar los datos de la vista actual
  if (lastSuccess !== null && s.last_success && s.last_success !== lastSuccess) {
    invalidatePlayers();
    toast('Datos actualizados');
    const v = (location.hash.slice(1) || 'inicio').split(/[/?]/)[0];
    if (['inicio', 'jugadores', 'heroe', 'climbers', 'equipos', ''].includes(v)) route();
  }
  lastSuccess = s.last_success || 0;
  setTimeout(pollStatus, s.running ? 2000 : 20000);
}

window.addEventListener('hashchange', route);
initSearch(document.getElementById('gsearch'), ctx);
pollStatus().then(route);

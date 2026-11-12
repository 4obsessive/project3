// Router por hash + barra de estado de la actualización.
import { api, invalidatePlayers } from './api.js';
import { el, fmt, toast } from './util.js';

const VIEWS = {
  jugadores: () => import('./views/players.js'),
  heroe: () => import('./views/hero.js'),
  climbers: () => import('./views/climbers.js'),
  equipos: () => import('./views/teams.js'),
  partidas: () => import('./views/matches.js'),
  informe: () => import('./views/report.js'),
  ajustes: () => import('./views/settings.js'),
};

const ctx = { status: null, teamNames: { 0: 'Hidden King', 1: 'Archmother' }, params: [], query: {} };
let lastSuccess = null, renderSeq = 0;

async function route() {
  const raw = location.hash.slice(1) || 'jugadores';
  const [pathPart, qs] = raw.split('?');
  const [name, ...params] = pathPart.split('/');
  const view = VIEWS[name] ? name : 'jugadores';
  ctx.params = params.map(decodeURIComponent);
  ctx.query = Object.fromEntries(new URLSearchParams(qs || ''));
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.view === view));
  const root = document.getElementById('view');
  document.getElementById('drawer').hidden = true;
  const seq = ++renderSeq;
  root.innerHTML = '';
  try {
    const mod = await VIEWS[view]();
    if (seq !== renderSeq) return;
    await mod.render(root, ctx);
  } catch (e) {
    console.error(e);
    root.append(el('div', { class: 'panel' }, el('h3', {}, 'Error'), el('p', {}, e.message)));
  }
}
ctx.onPlayersChanged = () => { if ((location.hash || '#jugadores').startsWith('#jugadores')) route(); };

async function pollStatus() {
  let s;
  try { s = await api.get('/api/status'); } catch { setTimeout(pollStatus, 10000); return; }
  ctx.status = s;
  const box = document.getElementById('status');
  box.innerHTML = '';
  if (s.running) {
    const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
    box.append(el('span', { class: 'spinner' }), el('span', {}, `${s.label || 'Actualizando'}${s.message ? ' · ' + s.message : ''}`),
      el('div', { class: 'progress', title: `${s.done}/${s.total}` }, el('div', { style: { width: pct + '%' } })));
  } else {
    if (s.error) box.append(el('span', { style: { color: 'var(--bad)' }, title: s.error }, 'Error en la última actualización (se reanudará)'));
    box.append(el('span', {}, `Actualizado ${fmt.ago(s.last_success)}`),
      s.next_run ? el('span', {}, `· próxima ${fmt.datetime(s.next_run)}`) : null);
  }
  box.append(el('span', {}, `· ${s.counts.players} jugadores`),
    el('button', { disabled: s.running, onclick: async () => { try { const r = await api.post('/api/update'); toast(r.message); pollStatus(); } catch (e) { toast(e.message, true); } } }, 'Actualizar ahora'));
  // cuando termina una actualización, refrescar los datos de la vista actual
  if (lastSuccess !== null && s.last_success && s.last_success !== lastSuccess) {
    invalidatePlayers();
    toast('Datos actualizados');
    const v = (location.hash.slice(1) || 'jugadores').split(/[/?]/)[0];
    if (['jugadores', 'heroe', 'climbers', 'equipos', ''].includes(v)) route();
  }
  lastSuccess = s.last_success || 0;
  setTimeout(pollStatus, s.running ? 2000 : 20000);
}

window.addEventListener('hashchange', route);
pollStatus().then(route);

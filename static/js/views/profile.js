// Panel lateral de perfil: stats, top héroes, cuentas, tendencias, dúos y campos manuales.
import { api, invalidatePlayers, getHeroes, getPlayers } from '../api.js';
import { el, fmt, dataTable, toast, errorBox, cssVar } from '../util.js';
import { lines } from '../charts.js';
import { heroArt, rankEmblem, scoreRing, wrBar, confidencePips, roleStack, formStrip, sparkline, statTile, sectionHead, emptyState, skeleton, tabs, getRanks, badgeName, windowText } from '../ui.js';
import { computeScores, loadWeights } from '../score.js';

const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];

export async function openProfile(pid, ctx) {
  const d = openDrawer();
  d.innerHTML = '';
  d.append(closeBtn(), el('h2', { id: 'drawer-title', class: 'sr-only' }, 'Perfil'), skeleton('drawer'));
  d.querySelector('.pf-close').focus();
  let p;
  try { p = await api.get(`/api/players/${pid}?duos=0`); } catch (e) { d.innerHTML = ''; d.append(closeBtn(), el('h2', { id: 'drawer-title', class: 'sr-only' }, 'Perfil'), errorBox(e.message, () => openProfile(pid, ctx))); d.querySelector('.pf-close').focus(); return; }
  const [heroes, ranks] = await Promise.all([getHeroes().catch(() => []), getRanks()]);
  const heroById = new Map(heroes.map(h => [h.id, h]));
  const heroOf = h => heroById.get(h.hero_id) || { id: h.hero_id, name: h.name };
  const players = await getPlayers().catch(() => []);
  const weights = loadWeights();
  computeScores(players, weights);
  const me = players.find(x => x.id === p.id) || p;
  computeScores([p], weights);
  const s = p.stats;
  const main = p.heroes[0] ? heroOf(p.heroes[0]) : null;
  d.innerHTML = '';

  // ---------------------------------------------------------------- banner
  const statusSel = el('select', { 'aria-label': 'Estado de seguimiento' }, STATUSES.map(v => el('option', { selected: p.manual.status === v }, v)));
  statusSel.addEventListener('change', async () => {
    try { await api.post(`/api/players/${pid}/manual`, { status: statusSel.value }); invalidatePlayers(); toast('Estado guardado'); ctx.onPlayersChanged?.(); } catch (e) { toast(e.message, true); }
  });
  const avatar = p.avatar ? el('img', { class: 'pf-avatar', src: p.avatar.replace('_medium.jpg', '_full.jpg'), alt: '' }) : null;
  if (avatar) avatar.addEventListener('error', () => { if (!avatar.src.endsWith('_medium.jpg')) avatar.src = p.avatar; else avatar.remove(); });
  const prevRanks = Object.entries(p.ranks).filter(([k]) => +k !== ctx.status?.current_leaderboard_id).map(([k, v]) => `#${v} en ${(ctx.status?.season_names || {})[k] || k}`);
  d.append(el('div', { class: 'pf-banner' },
    el('div', { class: 'pf-bg', 'aria-hidden': 'true' }, main ? heroArt(main, { size: 'card', kind: 'bg' }) : null),
    closeBtn(),
    avatar,
    el('div', { class: 'pf-id' },
      el('h2', { id: 'drawer-title' }, p.name),
      el('div', { class: 'pf-meta' },
        p.badge ? rankEmblem(p.badge, ranks, { size: 'lg' }) : null,
        el('span', {}, p.rank ? `#${p.rank} temporada actual` : 'fuera de la leaderboard actual'),
        prevRanks.length ? el('span', { class: 'muted' }, prevRanks.join(' · ')) : null),
      el('div', { class: 'pf-meta' },
        p.team ? el('span', {}, 'Equipo: ', el('b', {}, p.team)) : el('span', { style: { color: 'var(--spirit)' } }, 'Libre'),
        el('a', { href: p.steam_url, target: '_blank', rel: 'noopener' }, 'Steam ↗'),
        p.steam_name && p.steam_name !== p.name ? el('span', { class: 'muted' }, `Steam: ${p.steam_name}`) : null,
        statusSel))));

  // ---------------------------------------------------------------- tiles
  const body = el('div', { class: 'pf-body' });
  d.append(body);
  body.append(el('p', { class: 'muted small', style: { margin: '0 0 12px' } }, windowText(p.window, s.matches)),
    el('div', { class: 'pf-tiles' },
      statTile('Score', scoreRing(me.score ?? p.score_default, { lo: me._lo, hi: me._hi, size: 40, provisional: p.provisional }),
        { sub: p.provisional ? 'provisional (<20 partidas)' : `banda ${fmt.int(me._lo)}–${fmt.int(me._hi)}` }),
      statTile('Winrate', fmt.pct(s.winrate), { sub: s.wr_lo != null ? `IC95 ${fmt.pct(s.wr_lo)}–${fmt.pct(s.wr_hi)} · ajustado ${fmt.pct(s.wr_adj)}` : '' }),
      statTile('KDA idx', fmt.dec(s.idx_kda), { sub: `KDA ${fmt.dec(s.kda)} · 1.00 = media en sus héroes` }),
      statTile('Daño/min', fmt.int(s.dmg_per_min), { sub: `índice ${fmt.dec(s.idx_dmg)}` }),
      statTile('Oro/min', fmt.int(s.nw_per_min), { sub: `índice ${fmt.dec(s.idx_nw)}` }),
      statTile('Partidas', fmt.int(s.matches), { extra: el('span', { class: 'tile-sub' }, confidencePips(p.reliability, { wr: s.winrate, n: s.matches, lo: s.wr_lo, hi: s.wr_hi }), ' ', p.reliability) })));

  // ---------------------------------------------------------------- pestañas
  const panes = {};
  const TABS = [['resumen', 'Resumen'], ['heroes', 'Héroes'], ['tendencias', 'Tendencias'], ['duos', 'Dúos'], ['seguimiento', 'Seguimiento']];
  const tabBar = tabs(TABS.map(([id, label]) => ({ id: 'pf-' + id, label })), { label: 'Secciones del perfil', onChange: id => {
    for (const [k, pane] of Object.entries(panes)) pane.hidden = 'pf-' + k !== id;
    if (id === 'pf-duos') loadDuos();
  } });
  body.append(tabBar);
  for (const [id] of TABS) {
    panes[id] = el('div', { role: 'tabpanel', id: `pane-${id}`, 'aria-labelledby': `tab-pf-${id}`, tabindex: '0', hidden: id !== 'resumen' });
    body.append(panes[id]);
  }

  // Resumen
  const h = p.history;
  panes.resumen.append(
    sectionHead('Roles'), roleStack(p),
    sectionHead('Top héroes', el('span', { class: 'sub' }, 'WR con intervalo · partidas')),
    p.heroes.length ? el('div', { class: 'pf-heroes' }, p.heroes.slice(0, 5).map(x => el('div', { class: 'pf-hero' },
      heroArt(heroOf(x), { size: 'card', label: true }),
      wrBar(x.winrate, { lo: x.wr_lo, hi: x.wr_hi, muted: x.matches < 20, n: x.matches }),
      el('span', { class: 'meta' }, el('span', {}, `${fmt.int(x.matches)} partidas`), el('span', {}, `KDA ${fmt.dec(x.kda)}`)))))
      : emptyState('Sin héroes registrados en el periodo.'),
    sectionHead('Forma', h ? el('span', { class: 'sub' }, `${h.ranked_only ? 'ranked · ' : ''}${h.matches} partidas en 60 días`) : null),
    h ? el('div', { class: 'row', style: { gap: '16px' } },
      formStrip(h.last20),
      el('span', { class: 'small' }, h.streak > 0 ? `Racha: ${h.streak} victorias` : h.streak < 0 ? `Racha: ${-h.streak} derrotas` : ''),
      h.recency_wr != null ? el('span', { class: 'small muted', title: 'Cada partida pesa la mitad cada 14 días' }, `WR reciente ponderado ${fmt.pct(h.recency_wr)}`) : null,
      h.kda_iqr != null ? el('span', { class: 'small muted', title: 'Rango intercuartílico del KDA por partida: más bajo = más constante' }, `Consistencia (IQR KDA) ${fmt.dec(h.kda_iqr, 1)}`) : null)
      : el('p', { class: 'muted small' }, 'El historial de partidas se descarga al abrir el perfil (puede tardar unos segundos la primera vez).'),
    sectionHead('Rango'),
    badgeBlock(p, ranks));

  // Héroes
  panes.heroes.append(dataTable([
    { key: 'name', label: 'Héroe', render: x => el('span', { class: 'hero-cell' }, heroArt(heroOf(x), { size: 'mini' }), x.name) },
    { key: 'matches', label: 'Partidas', num: true },
    { key: 'winrate', label: 'WR', num: true, sort: x => x.wr_adj, render: x => wrBar(x.winrate, { lo: x.wr_lo, hi: x.wr_hi, muted: x.matches < 20, n: x.matches }) },
    { key: 'wr_adj', label: 'WR ajust.', num: true, fmt: 'pct', title: 'Encogido hacia el winrate medio de los jugadores seguidos en ese héroe' },
    { key: 'kda', label: 'KDA', num: true, fmt: '2' },
    { key: 'idx_kda', label: 'KDA idx', num: true, fmt: '2' },
    { key: 'dmg_per_min', label: 'Daño/min', num: true, fmt: 'int' },
    { key: 'nw_per_min', label: 'Oro/min', num: true, fmt: 'int' },
    { key: 'reliability', label: 'Confianza', render: x => confidencePips(x.reliability, { wr: x.winrate, n: x.matches, lo: x.wr_lo, hi: x.wr_hi }) },
  ], p.heroes, { sortKey: 'matches', label: 'Héroes del jugador' }));

  // Tendencias
  const tr = p.trends;
  const weekly = h?.weekly || [];
  if (weekly.length >= 3) {
    panes.tendencias.append(sectionHead('Winrate semanal', el('span', { class: 'sub' }, 'banda = IC95 de cada semana')),
      lines({ series: [{ name: 'WR semanal', points: weekly.map(w => [w.t, w.winrate * 100]), band: weekly.map(w => [w.t, w.lo * 100, w.hi * 100]), ref: 50, color: cssVar('--gold') }],
        label: 'Winrate semanal', yfmt: v => Math.round(v) + '%' }));
  } else panes.tendencias.append(sectionHead('Winrate semanal'), emptyState('Hacen falta al menos 3 semanas con partidas para dibujar la tendencia.', { ico: 'climbers' }));
  if (tr.rank.length >= 3) {
    panes.tendencias.append(sectionHead('Posición en la leaderboard'),
      lines({ series: [{ name: 'rank', points: tr.rank.map(r => [r.t, r.rank]), color: cssVar('--spirit') }], invert: true, label: 'Posición en la leaderboard', yfmt: v => '#' + Math.round(v) }));
  } else panes.tendencias.append(sectionHead('Posición en la leaderboard'), emptyState('Aún no hay suficientes snapshots de la leaderboard (mínimo 3).', { ico: 'climbers' }));
  const bl = h?.badge_line || [];
  if (bl.length >= 3) {
    panes.tendencias.append(sectionHead('Badge por partida'),
      lines({ series: [{ name: 'badge', points: bl.map(b => [b.t, b.badge]), color: cssVar('--c5') }], label: 'Badge por partida', yfmt: v => badgeName(Math.round(v), ranks) || Math.round(v) }));
  }
  if (tr.stats.length >= 3) {
    panes.tendencias.append(sectionHead('KDA', el('span', { class: 'sub' }, 'media móvil 30 d (cada punto es la ventana completa)')),
      lines({ series: [{ name: 'KDA', points: tr.stats.map(r => [r.t, r.kda]), color: cssVar('--c2') }], label: 'KDA, media móvil de 30 días' }));
  }

  // Seguimiento (contacto, cuentas)
  const form = {};
  const field = (key, input) => { form[key] = input; input.id = 'pf-' + key; return input; };
  const lab = (key, text) => el('label', { for: 'pf-' + key }, text);
  const m = p.manual;
  const accBox = el('div');
  accBox.append(dataTable([
    { key: 'account_id', label: 'Cuenta', render: a => el('a', { href: a.steam_url, target: '_blank', rel: 'noopener' }, a.account_id) },
    { key: 'steam_name', label: 'Nombre Steam', render: a => a.steam_name || '–' },
    { key: 'source', label: 'Origen' }, { key: 'badge', label: 'Rango', render: a => a.badge ? rankEmblem(a.badge, ranks) : '–' },
    { key: 'x', label: '', sortable: false, render: a => a.account_id === p.primary_account_id ? el('span', { class: 'muted small' }, 'principal') :
        el('button', { class: 'small', onclick: async () => { try { await api.post(`/api/players/${pid}/unlink`, { account: a.account_id }); invalidatePlayers(); openProfile(pid, ctx); } catch (e) { toast(e.message, true); } } }, 'Separar') },
  ], p.accounts));
  const linkInput = el('input', { placeholder: 'ID, [U:1:N], steam64 o URL de perfil', 'aria-label': 'Cuenta a enlazar', style: { minWidth: '240px', flex: '1' } });
  panes.seguimiento.append(
    sectionHead('Contacto y seguimiento'),
    el('p', { class: 'muted small' }, 'Solo lo que el jugador hace público. Nunca se guarda la edad exacta. Estos campos no se tocan al actualizar.'),
    el('div', { class: 'form-grid' },
      lab('twitter', 'Twitter/X'), field('twitter', el('input', { value: m.twitter || '' })),
      lab('twitch', 'Twitch'), field('twitch', el('input', { value: m.twitch || '' })),
      lab('discord', 'Discord'), field('discord', el('input', { value: m.discord || '' })),
      lab('adult', 'Mayor de edad'), field('adult', el('select', {}, ['desconocido', 'sí', 'no'].map(v => el('option', { selected: m.adult === v }, v)))),
      lab('team', 'Equipo (manual)'), field('team', el('input', { value: m.team || '', placeholder: p.team_source === 'equipos.txt' ? `${p.team} (equipos.txt)` : '' })),
      lab('notes', 'Notas'), field('notes', el('textarea', {}, m.notes || ''))),
    sectionHead('Cuentas'), el('p', { class: 'muted small' }, 'Las stats de todas las cuentas enlazadas se suman.'), accBox,
    el('div', { class: 'row', style: { marginTop: '8px' } }, linkInput, el('button', { type: 'button', onclick: async () => {
      try { await api.post(`/api/players/${pid}/link`, { account: linkInput.value }); invalidatePlayers(); toast('Cuenta enlazada (sus stats llegan en la próxima actualización si es nueva)'); openProfile(pid, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Enlazar cuenta')),
    el('div', { class: 'pf-sticky' }, el('button', { type: 'button', class: 'primary', onclick: async () => {
      const b = { status: statusSel.value }; for (const [k, i] of Object.entries(form)) b[k] = i.value;
      try { await api.post(`/api/players/${pid}/manual`, b); invalidatePlayers(); toast('Guardado'); ctx.onPlayersChanged?.(); } catch (e) { toast(e.message, true); }
    } }, 'Guardar'), el('span', { class: 'muted small' }, 'Guarda contacto, equipo, notas y estado.')));

  // Dúos (petición aparte y perezosa: tarda un poco)
  let duosLoaded = false;
  async function loadDuos() {
    if (duosLoaded) return;
    duosLoaded = true;
    const box = panes.duos;
    box.append(skeleton('rows'));
    try {
      const full = await api.get(`/api/players/${pid}`);
      box.innerHTML = '';
      const du = full.duos;
      if (!du || du.error) { box.append(emptyState(du?.error || 'Sin datos de compañeros.')); return; }
      const nameCell = r => r.player_id ? el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(r.player_id, ctx) }, r.name || String(r.account_id)) : (r.name || String(r.account_id));
      box.append(sectionHead('Top 5 dúos', el('span', { class: 'sub' }, `${du.days} días`)), el('p', { class: 'muted small' }, du.note),
        du.duos.length ? dataTable([
          { key: 'name', label: 'Compañero', render: nameCell }, { key: 'duo_matches', label: 'Partidas en dúo', num: true },
          { key: 'duo_winrate', label: 'WR en dúo', num: true, render: r => r.duo_winrate == null ? '–' : `${fmt.pct(r.duo_winrate)} (${r.duo_results_known})` },
          { key: 'party_matches', label: 'En grupo (total)', num: true },
        ], du.duos, { sortKey: 'duo_matches' }) : emptyState('Sin dúos en los últimos 30 días.'),
        sectionHead('Compañeros de grupo', el('span', { class: 'sub' }, 'incluye tríos y stacks')),
        dataTable([{ key: 'name', label: 'Compañero', render: nameCell }, { key: 'party_matches', label: 'Partidas', num: true }, { key: 'party_winrate', label: 'WR', fmt: 'pct', num: true }], du.party_mates, { sortKey: 'party_matches' }));
    } catch (e) {
      box.innerHTML = ''; box.append(emptyState('No se pudieron cargar los dúos: ' + e.message));
    }
  }
  d.scrollTop = 0;
}

function badgeBlock(p, ranks) {
  const series = (p.trends?.badge || []).filter(b => b.badge);
  const box = el('div', { class: 'row', style: { gap: '16px' } });
  if (p.badge) box.append(rankEmblem(p.badge, ranks, { size: 'lg' }));
  else box.append(el('span', { class: 'muted small' }, 'Sin rango conocido.'));
  if (p.flat_progress != null) box.append(el('span', { class: 'small muted', title: 'Progreso continuo de rango tras la última partida (más alto = mejor)' }, `Progreso ${fmt.int(p.flat_progress)}`));
  const sp = sparkline(series.map(b => b.flat ?? b.badge), { w: 140, h: 28 });
  if (sp) box.append(sp);
  return box;
}

function closeBtn() {
  return el('button', { type: 'button', class: 'pf-close', 'aria-label': 'Cerrar perfil', onclick: () => closeDrawer() }, el('span', { 'aria-hidden': 'true' }, '✕'));
}

// ---- diálogo: foco, Esc, fondo clicable
let returnFocus = null;
function openDrawer() {
  const d = document.getElementById('drawer');
  if (d.hidden) returnFocus = document.activeElement;
  d.setAttribute('aria-labelledby', 'drawer-title');
  d.removeAttribute('aria-label');
  if (d.hidden) {
    d.classList.add('opening');
    requestAnimationFrame(() => requestAnimationFrame(() => d.classList.remove('opening')));
  }
  d.hidden = false;
  document.getElementById('backdrop').hidden = false;
  return d;
}
export function closeDrawer(restore = true) {
  const d = document.getElementById('drawer');
  if (d.hidden) return;
  d.hidden = true;
  document.getElementById('backdrop').hidden = true;
  if (restore && returnFocus && document.contains(returnFocus)) returnFocus.focus();
  returnFocus = null;
}
document.getElementById('backdrop')?.addEventListener('click', () => closeDrawer());
document.addEventListener('keydown', e => {
  const d = document.getElementById('drawer');
  if (d.hidden) return;
  if (e.key === 'Escape') { e.preventDefault(); closeDrawer(); return; }
  if (e.key !== 'Tab') return;
  // trampa de foco dentro del diálogo
  const f = [...d.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')].filter(x => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (!d.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

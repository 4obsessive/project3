// Panel lateral de perfil: stats, top héroes, cuentas, tendencias, dúos y campos manuales.
import { api, invalidatePlayers } from '../api.js';
import { el, fmt, dataTable, toast, spinner, errorBox, cssVar } from '../util.js';
import { lines } from '../charts.js';

const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];

export async function openProfile(pid, ctx) {
  const d = openDrawer();
  d.innerHTML = '';
  d.append(head('Perfil'), spinner('Cargando perfil…'));
  d.querySelector('.close').focus();
  let p;
  try { p = await api.get(`/api/players/${pid}?duos=0`); } catch (e) { d.innerHTML = ''; d.append(head('Perfil'), errorBox(e.message, () => openProfile(pid, ctx))); d.querySelector('.close').focus(); return; }
  d.innerHTML = '';
  const s = p.stats;
  d.append(
    head(p.name),
    el('div', { class: 'row muted' },
      [p.rank ? `#${p.rank} temporada actual` : 'fuera de la leaderboard actual',
        ...Object.entries(p.ranks).filter(([k]) => +k !== ctx.status?.current_leaderboard_id).map(([k, v]) => `#${v} en ${(ctx.status?.season_names || {})[k] || k}`),
        p.team ? `equipo: ${p.team}` : 'libre'].join(' · '),
      el('a', { href: p.steam_url, target: '_blank', rel: 'noopener' }, 'Steam ↗')),
    el('div', { class: 'kv', style: { margin: '12px 0' } },
      kv(fmt.int(s.matches), 'partidas (30 d)'), kv(fmt.pct(s.winrate), 'winrate'), kv(fmt.dec(s.kd), 'KD'), kv(fmt.dec(s.kda), 'KDA'),
      kv(fmt.int(s.damage_per_match), 'daño / partida'), kv(fmt.int(s.obj_damage_per_min), 'daño a objetivos / min'),
      kv(p.reliability, 'fiabilidad'), kv(el('span', { class: 'roles' }, p.role_text || '–'), 'roles')),
  );

  // top 5 héroes
  d.append(el('h3', {}, 'Top 5 héroes del mes'), dataTable([
    { key: 'name', label: 'Héroe' }, { key: 'matches', label: 'Partidas' }, { key: 'winrate', label: 'WR', fmt: 'pct' },
    { key: 'kd', label: 'KD', fmt: '2' }, { key: 'kda', label: 'KDA', fmt: '2' }, { key: 'damage_per_match', label: 'Daño/partida', fmt: 'int' },
  ], p.top_heroes, { sortKey: 'matches' }));
  if (p.heroes.length > 5) {
    const all = el('details', {}, el('summary', { class: 'muted small' }, `Todos los héroes (${p.heroes.length})`),
      dataTable([{ key: 'name', label: 'Héroe' }, { key: 'matches', label: 'Partidas' }, { key: 'winrate', label: 'WR', fmt: 'pct' }, { key: 'kda', label: 'KDA', fmt: '2' }], p.heroes, { sortKey: 'matches' }));
    d.append(all);
  }

  // campos manuales
  const form = {};
  const field = (key, input) => { form[key] = input; input.id = 'pf-' + key; return input; };
  const lab = (key, text) => el('label', { for: 'pf-' + key }, text);
  const m = p.manual;
  d.append(el('h3', { style: { marginTop: '16px' } }, 'Contacto y seguimiento (manual)'),
    el('p', { class: 'muted small' }, 'Solo lo que el jugador hace público. Nunca se guarda la edad exacta. Estos campos no se tocan al actualizar.'),
    el('div', { class: 'form-grid' },
      lab('twitter', 'Twitter/X'), field('twitter', el('input', { value: m.twitter || '' })),
      lab('twitch', 'Twitch'), field('twitch', el('input', { value: m.twitch || '' })),
      lab('discord', 'Discord'), field('discord', el('input', { value: m.discord || '' })),
      lab('adult', 'Mayor de edad'), field('adult', el('select', {}, ['desconocido', 'sí', 'no'].map(v => el('option', { selected: m.adult === v }, v)))),
      lab('status', 'Estado'), field('status', el('select', {}, STATUSES.map(v => el('option', { selected: m.status === v }, v)))),
      lab('team', 'Equipo (manual)'), field('team', el('input', { value: m.team || '', placeholder: p.team_source === 'equipos.txt' ? `${p.team} (equipos.txt)` : '' })),
      lab('notes', 'Notas'), field('notes', el('textarea', {}, m.notes || '')),
    ),
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { class: 'primary', onclick: async () => {
      const body = {}; for (const [k, i] of Object.entries(form)) body[k] = i.value;
      try { await api.post(`/api/players/${pid}/manual`, body); invalidatePlayers(); toast('Guardado'); ctx.onPlayersChanged?.(); } catch (e) { toast(e.message, true); }
    } }, 'Guardar')));

  // cuentas
  const accBox = el('div');
  const renderAccounts = list => {
    accBox.innerHTML = '';
    accBox.append(dataTable([
      { key: 'account_id', label: 'Cuenta', render: a => el('a', { href: a.steam_url, target: '_blank', rel: 'noopener' }, a.account_id) },
      { key: 'steam_name', label: 'Nombre Steam', render: a => a.steam_name || '–' },
      { key: 'source', label: 'Origen' }, { key: 'badge', label: 'Badge', render: a => a.badge ?? '–' },
      { key: 'x', label: '', sortable: false, render: a => a.account_id === p.primary_account_id ? el('span', { class: 'muted small' }, 'principal') :
          el('button', { class: 'small', onclick: async () => { try { await api.post(`/api/players/${pid}/unlink`, { account: a.account_id }); invalidatePlayers(); openProfile(pid, ctx); } catch (e) { toast(e.message, true); } } }, 'Separar') },
    ], list));
  };
  renderAccounts(p.accounts);
  const linkInput = el('input', { placeholder: 'ID, [U:1:N], steam64 o URL de perfil', 'aria-label': 'Cuenta a enlazar', style: { minWidth: '260px' } });
  d.append(el('h3', { style: { marginTop: '16px' } }, 'Cuentas'), el('p', { class: 'muted small' }, 'Las stats de todas las cuentas enlazadas se suman.'), accBox,
    el('div', { class: 'row', style: { marginTop: '6px' } }, linkInput, el('button', { onclick: async () => {
      try { await api.post(`/api/players/${pid}/link`, { account: linkInput.value }); invalidatePlayers(); toast('Cuenta enlazada (sus stats llegan en la próxima actualización si es nueva)'); openProfile(pid, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Enlazar cuenta')));

  // tendencias
  const tr = p.trends;
  d.append(el('h3', { style: { marginTop: '16px' } }, 'Tendencias'),
    el('div', { class: 'chart-title' }, 'Posición en la leaderboard (temporada actual)'),
    lines({ series: [{ name: 'rank', points: tr.rank.map(r => [r.t, r.rank]), color: cssVar('--c1') }], invert: true, label: 'Posición en la leaderboard', yfmt: v => '#' + Math.round(v) }),
    el('div', { class: 'chart-title' }, 'KDA (ventana de 30 días en cada actualización)'),
    lines({ series: [{ name: 'KDA', points: tr.stats.map(r => [r.t, r.kda]), color: cssVar('--c2') }], label: 'KDA' }),
    el('div', { class: 'chart-title' }, 'Winrate'),
    lines({ series: [{ name: 'WR', points: tr.stats.map(r => [r.t, r.winrate == null ? null : r.winrate * 100]), color: cssVar('--c3') }], label: 'Winrate', yfmt: v => Math.round(v) + '%' }));

  // dúos (petición aparte: tarda un poco)
  const duoBox = el('div', {}, spinner('Buscando compañeros de grupo…'));
  d.append(el('h3', { style: { marginTop: '16px' } }, 'Top 5 dúos (30 días)'), duoBox);
  try {
    const full = await api.get(`/api/players/${pid}`);
    duoBox.innerHTML = '';
    const du = full.duos;
    if (du.error) { duoBox.append(el('p', { class: 'muted' }, du.error)); return; }
    const nameCell = r => r.player_id ? el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(r.player_id, ctx) }, r.name || String(r.account_id)) : (r.name || String(r.account_id));
    duoBox.append(el('p', { class: 'muted small' }, du.note),
      du.duos.length ? dataTable([
        { key: 'name', label: 'Compañero', render: nameCell }, { key: 'duo_matches', label: 'Partidas en dúo' },
        { key: 'duo_winrate', label: 'WR en dúo', render: r => r.duo_winrate == null ? '–' : `${fmt.pct(r.duo_winrate)} (${r.duo_results_known})` },
        { key: 'party_matches', label: 'En grupo (total)' },
      ], du.duos, { sortKey: 'duo_matches' }) : el('p', { class: 'muted' }, 'Sin dúos en los últimos 30 días.'),
      el('h4', { style: { marginTop: '10px' } }, 'Compañeros de grupo (incluye tríos y stacks)'),
      dataTable([{ key: 'name', label: 'Compañero', render: nameCell }, { key: 'party_matches', label: 'Partidas' }, { key: 'party_winrate', label: 'WR', fmt: 'pct' }], du.party_mates, { sortKey: 'party_matches' }));
  } catch (e) {
    duoBox.innerHTML = ''; duoBox.append(el('p', { class: 'muted' }, 'No se pudieron cargar los dúos: ' + e.message));
  }
}

function kv(v, label) { return el('div', {}, el('b', {}, v), el('span', {}, label)); }
function head(title) {
  return el('div', { class: 'drawer-head' }, el('h2', { id: 'drawer-title' }, title),
    el('button', { type: 'button', class: 'close', 'aria-label': 'Cerrar perfil', onclick: () => closeDrawer() }, el('span', { 'aria-hidden': 'true' }, '✕')));
}

// ---- diálogo: foco, Esc, fondo clicable
let returnFocus = null;
function openDrawer() {
  const d = document.getElementById('drawer');
  if (d.hidden) returnFocus = document.activeElement;
  d.setAttribute('aria-labelledby', 'drawer-title');
  d.removeAttribute('aria-label');
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

// Profile side panel: stats, top heroes, accounts, trends, duos and manual fields.
import { api, invalidatePlayers, getHeroes, getPlayers, normalizePlayer } from '../api.js';
import { el, fmt, dataTable, toast, errorBox, cssVar } from '../util.js';
import { lines } from '../charts.js';
import { heroArt, rankEmblem, scoreRing, wrBar, confidencePips, roleStack, formStrip, sparkline, statTile, sectionHead, emptyState, skeleton, tabs, getRanks, badgeName, windowText, cellBar, STATUS_LABEL, ADULT_LABEL } from '../ui.js';
import { computeScores, loadWeights } from '../score.js';

const STATUSES = ['pendiente', 'en seguimiento', 'contactado', 'en prueba', 'fichado', 'descartado'];

export async function openProfile(pid, ctx) {
  const d = openDrawer();
  d.innerHTML = '';
  d.append(closeBtn(), el('h2', { id: 'drawer-title', class: 'sr-only' }, 'Profile'), skeleton('drawer'));
  d.querySelector('.pf-close').focus();
  let p;
  try { p = normalizePlayer(await api.get(`/api/players/${pid}?duos=0`)); } catch (e) { d.innerHTML = ''; d.append(closeBtn(), el('h2', { id: 'drawer-title', class: 'sr-only' }, 'Profile'), errorBox(e.message, () => openProfile(pid, ctx))); d.querySelector('.pf-close').focus(); return; }
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
  const statusSel = el('select', { 'aria-label': 'Tracking status' }, STATUSES.map(v => el('option', { value: v, selected: p.manual.status === v }, STATUS_LABEL[v] || v)));
  statusSel.addEventListener('change', async () => {
    try { await api.post(`/api/players/${pid}/manual`, { status: statusSel.value }); invalidatePlayers(); toast('Status saved'); ctx.onPlayersChanged?.(); } catch (e) { toast(e.message, true); }
  });
  const avatar = p.avatar ? el('img', { class: 'pf-avatar', src: p.avatar.replace('_medium.jpg', '_full.jpg'), alt: '' }) : null;
  if (avatar) avatar.addEventListener('error', () => { if (!avatar.src.endsWith('_medium.jpg')) avatar.src = p.avatar; else avatar.remove(); });
  const prevRanks = Object.entries(p.ranks).filter(([k]) => +k !== ctx.status?.current_leaderboard_id).map(([k, v]) => `#${v} in ${(ctx.status?.season_names || {})[k] || k}`);
  d.append(el('div', { class: 'pf-banner' },
    el('div', { class: 'pf-bg', 'aria-hidden': 'true' }, main ? heroArt(main, { size: 'card', kind: 'bg' }) : null),
    closeBtn(),
    avatar,
    el('div', { class: 'pf-id' },
      el('h2', { id: 'drawer-title' }, p.name),
      el('div', { class: 'pf-meta' },
        p.badge ? rankEmblem(p.badge, ranks, { size: 'lg' }) : null,
        el('span', {}, p.rank ? `#${p.rank} current season` : 'off the current leaderboard'),
        prevRanks.length ? el('span', { class: 'muted' }, prevRanks.join(' · ')) : null),
      el('div', { class: 'pf-meta' },
        p.team ? el('span', {}, 'Team: ', el('b', {}, p.team)) : el('span', { style: { color: 'var(--spirit)' } }, 'Free agent'),
        el('a', { href: p.steam_url, target: '_blank', rel: 'noopener' }, 'Steam ↗'),
        p.steam_name && p.steam_name !== p.name ? el('span', { class: 'muted' }, `Steam: ${p.steam_name}`) : null,
        statusSel))));

  // ---------------------------------------------------------------- tiles
  const body = el('div', { class: 'pf-body' });
  d.append(body);
  body.append(el('p', { class: 'muted small', style: { margin: '0 0 12px' } }, windowText(p.window, s.matches)),
    el('div', { class: 'pf-tiles' },
      statTile('Score', scoreRing(me.score ?? p.score_default, { lo: me._lo, hi: me._hi, size: 40, provisional: p.provisional }),
        { sub: p.provisional ? 'provisional (<20 matches)' : `band ${fmt.int(me._lo)}–${fmt.int(me._hi)}` }),
      statTile('Winrate', fmt.pct(s.winrate), { sub: s.wr_lo != null ? `95% CI ${fmt.pct(s.wr_lo)}–${fmt.pct(s.wr_hi)} · adjusted ${fmt.pct(s.wr_adj)}` : '' }),
      statTile('KDA idx', fmt.dec(s.idx_kda), { sub: `KDA ${fmt.dec(s.kda)} · 1.00 = average on their heroes` }),
      statTile('Damage/min', fmt.int(s.dmg_per_min), { sub: `index ${fmt.dec(s.idx_dmg)}` }),
      statTile('Gold/min', fmt.int(s.nw_per_min), { sub: `index ${fmt.dec(s.idx_nw)}` }),
      statTile('Matches', fmt.int(s.matches), { extra: el('span', { class: 'tile-sub' }, confidencePips(p.reliability, { wr: s.winrate, n: s.matches, lo: s.wr_lo, hi: s.wr_hi }), ' ', p.reliability) })));

  // ---------------------------------------------------------------- tabs
  const panes = {};
  const TABS = [['resumen', 'Summary'], ['heroes', 'Heroes'], ['tendencias', 'Trends'], ['duos', 'Duos'], ['seguimiento', 'Tracking']];
  const tabBar = tabs(TABS.map(([id, label]) => ({ id: 'pf-' + id, label })), { label: 'Profile sections', onChange: id => {
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
    sectionHead('Top heroes', el('span', { class: 'sub' }, 'WR with interval · matches')),
    p.heroes.length ? el('div', { class: 'pf-heroes' }, p.heroes.slice(0, 5).map(x => el('div', { class: 'pf-hero' },
      heroArt(heroOf(x), { size: 'card', label: true }),
      wrBar(x.winrate, { lo: x.wr_lo, hi: x.wr_hi, muted: x.matches < 20, n: x.matches }),
      el('span', { class: 'meta' }, el('span', {}, `${fmt.int(x.matches)} matches`), el('span', {}, `KDA ${fmt.dec(x.kda)}`)))))
      : emptyState('No heroes recorded in this period.'),
    sectionHead('Form', h ? el('span', { class: 'sub' }, `${h.ranked_only ? 'ranked · ' : ''}${h.matches} matches in 60 days`) : null),
    h ? el('div', { class: 'row', style: { gap: '16px' } },
      formStrip(h.last20),
      el('span', { class: 'small' }, h.streak > 0 ? `Streak: ${h.streak} wins` : h.streak < 0 ? `Streak: ${-h.streak} losses` : ''),
      h.recency_wr != null ? el('span', { class: 'small muted', title: 'Each match weighs half as much every 14 days' }, `Recency-weighted WR ${fmt.pct(h.recency_wr)}`) : null,
      h.kda_iqr != null ? el('span', { class: 'small muted', title: 'Interquartile range of KDA per match: lower = more consistent' }, `Consistency (KDA IQR) ${fmt.dec(h.kda_iqr, 1)}`) : null)
      : el('p', { class: 'muted small' }, 'Match history is downloaded when the profile is opened (it can take a few seconds the first time).'),
    sectionHead('Rank'),
    badgeBlock(p, ranks));

  // Heroes
  const maxHeroM = Math.max(1, ...p.heroes.map(x => x.matches || 0));
  panes.heroes.append(dataTable([
    { key: 'name', label: 'Hero', render: x => el('span', { class: 'hero-cell' }, heroArt(heroOf(x), { size: 'mini' }), x.name) },
    { key: 'matches', label: 'Matches', num: true, render: x => cellBar(x.matches, maxHeroM, fmt.int(x.matches)) },
    { key: 'winrate', label: 'WR', num: true, sort: x => x.wr_adj, render: x => wrBar(x.winrate, { lo: x.wr_lo, hi: x.wr_hi, muted: x.matches < 20, n: x.matches }) },
    { key: 'wr_adj', label: 'Adj. WR', num: true, fmt: 'pct', title: 'Shrunk towards the average winrate of tracked players on that hero' },
    { key: 'kda', label: 'KDA', num: true, fmt: '2' },
    { key: 'idx_kda', label: 'KDA idx', num: true, fmt: '2' },
    { key: 'dmg_per_min', label: 'Damage/min', num: true, fmt: 'int' },
    { key: 'nw_per_min', label: 'Gold/min', num: true, fmt: 'int' },
    { key: 'reliability', label: 'Confidence', render: x => confidencePips(x.reliability, { wr: x.winrate, n: x.matches, lo: x.wr_lo, hi: x.wr_hi }) },
  ], p.heroes, { sortKey: 'matches', label: 'Player heroes' }));

  // Trends
  const tr = p.trends;
  const weekly = h?.weekly || [];
  if (weekly.length >= 3) {
    panes.tendencias.append(sectionHead('Weekly winrate', el('span', { class: 'sub' }, 'band = 95% CI of each week')),
      lines({ series: [{ name: 'Weekly WR', points: weekly.map(w => [w.t, w.winrate * 100]), band: weekly.map(w => [w.t, w.lo * 100, w.hi * 100]), ref: 50, color: cssVar('--gold') }],
        label: 'Weekly winrate', yfmt: v => Math.round(v) + '%' }));
  } else panes.tendencias.append(sectionHead('Weekly winrate'), emptyState('At least 3 weeks with matches are needed to draw the trend.', { ico: 'climbers' }));
  if (tr.rank.length >= 3) {
    panes.tendencias.append(sectionHead('Leaderboard position'),
      lines({ series: [{ name: 'rank', points: tr.rank.map(r => [r.t, r.rank]), color: cssVar('--spirit') }], invert: true, label: 'Leaderboard position', yfmt: v => '#' + Math.round(v) }));
  } else panes.tendencias.append(sectionHead('Leaderboard position'), emptyState('Not enough leaderboard snapshots yet (minimum 3).', { ico: 'climbers' }));
  const bl = h?.badge_line || [];
  if (bl.length >= 3) {
    panes.tendencias.append(sectionHead('Badge per match'),
      lines({ series: [{ name: 'badge', points: bl.map(b => [b.t, b.badge]), color: cssVar('--c5') }], label: 'Badge per match', yfmt: v => badgeName(Math.round(v), ranks) || Math.round(v) }));
  }
  if (tr.stats.length >= 3) {
    panes.tendencias.append(sectionHead('KDA', el('span', { class: 'sub' }, '30-day rolling average (each point is the full window)')),
      lines({ series: [{ name: 'KDA', points: tr.stats.map(r => [r.t, r.kda]), color: cssVar('--c2') }], label: 'KDA, 30-day rolling average' }));
  }

  // Tracking (contact, accounts)
  const form = {};
  const field = (key, input) => { form[key] = input; input.id = 'pf-' + key; return input; };
  const lab = (key, text) => el('label', { for: 'pf-' + key }, text);
  const m = p.manual;
  const accBox = el('div');
  accBox.append(dataTable([
    { key: 'account_id', label: 'Account', render: a => el('a', { href: a.steam_url, target: '_blank', rel: 'noopener' }, a.account_id) },
    { key: 'steam_name', label: 'Steam name', render: a => a.steam_name || '–' },
    { key: 'source', label: 'Source' }, { key: 'badge', label: 'Rank', render: a => a.badge ? rankEmblem(a.badge, ranks) : '–' },
    { key: 'x', label: '', sortable: false, render: a => a.account_id === p.primary_account_id ? el('span', { class: 'muted small' }, 'primary') :
        el('button', { class: 'small', onclick: async () => { try { await api.post(`/api/players/${pid}/unlink`, { account: a.account_id }); invalidatePlayers(); openProfile(pid, ctx); } catch (e) { toast(e.message, true); } } }, 'Unlink') },
  ], p.accounts));
  const linkInput = el('input', { placeholder: 'ID, [U:1:N], steam64 or profile URL', 'aria-label': 'Account to link', style: { minWidth: '240px', flex: '1' } });
  panes.seguimiento.append(
    sectionHead('Contact and tracking'),
    el('p', { class: 'muted small' }, 'Only what the player makes public. The exact age is never stored. These fields are not touched by updates.'),
    el('div', { class: 'form-grid' },
      lab('twitter', 'Twitter/X'), field('twitter', el('input', { value: m.twitter || '' })),
      lab('twitch', 'Twitch'), field('twitch', el('input', { value: m.twitch || '' })),
      lab('discord', 'Discord'), field('discord', el('input', { value: m.discord || '' })),
      lab('adult', 'Adult'), field('adult', el('select', {}, ['desconocido', 'sí', 'no'].map(v => el('option', { value: v, selected: m.adult === v }, ADULT_LABEL[v] || v)))),
      lab('team', 'Team (manual)'), field('team', el('input', { value: m.team || '', placeholder: p.team_source === 'equipos.txt' ? `${p.team} (equipos.txt)` : '' })),
      lab('notes', 'Notes'), field('notes', el('textarea', {}, m.notes || ''))),
    sectionHead('Accounts'), el('p', { class: 'muted small' }, 'Stats from all linked accounts are summed.'), accBox,
    el('div', { class: 'row', style: { marginTop: '8px' } }, linkInput, el('button', { type: 'button', onclick: async () => {
      try { await api.post(`/api/players/${pid}/link`, { account: linkInput.value }); invalidatePlayers(); toast('Account linked (its stats arrive with the next update if it is new)'); openProfile(pid, ctx); } catch (e) { toast(e.message, true); }
    } }, 'Link account')),
    el('div', { class: 'pf-sticky' }, el('button', { type: 'button', class: 'primary', onclick: async () => {
      const b = { status: statusSel.value }; for (const [k, i] of Object.entries(form)) b[k] = i.value;
      try { await api.post(`/api/players/${pid}/manual`, b); invalidatePlayers(); toast('Saved'); ctx.onPlayersChanged?.(); } catch (e) { toast(e.message, true); }
    } }, 'Save'), el('span', { class: 'muted small' }, 'Saves contact, team, notes and status.')));

  // Duos (separate lazy request: it takes a moment)
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
      if (!du || du.error) { box.append(emptyState(du?.error || 'No teammate data.')); return; }
      const nameCell = r => r.player_id ? el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(r.player_id, ctx) }, r.name || String(r.account_id)) : (r.name || String(r.account_id));
      box.append(sectionHead('Top 5 duos', el('span', { class: 'sub' }, `${du.days} days`)), el('p', { class: 'muted small' }, du.note),
        du.duos.length ? dataTable([
          { key: 'name', label: 'Teammate', render: nameCell }, { key: 'duo_matches', label: 'Duo matches', num: true },
          { key: 'duo_winrate', label: 'Duo WR', num: true, render: r => r.duo_winrate == null ? '–' : `${fmt.pct(r.duo_winrate)} (${r.duo_results_known})` },
          { key: 'party_matches', label: 'In party (total)', num: true },
        ], du.duos, { sortKey: 'duo_matches' }) : emptyState('No duos in the last 30 days.'),
        sectionHead('Party mates', el('span', { class: 'sub' }, 'includes trios and stacks')),
        dataTable([{ key: 'name', label: 'Teammate', render: nameCell }, { key: 'party_matches', label: 'Matches', num: true }, { key: 'party_winrate', label: 'WR', fmt: 'pct', num: true }], du.party_mates, { sortKey: 'party_matches' }));
    } catch (e) {
      box.innerHTML = ''; box.append(emptyState('Could not load duos: ' + e.message));
    }
  }
  d.scrollTop = 0;
}

function badgeBlock(p, ranks) {
  const series = (p.trends?.badge || []).filter(b => b.badge);
  const box = el('div', { class: 'row', style: { gap: '16px' } });
  if (p.badge) box.append(rankEmblem(p.badge, ranks, { size: 'lg' }));
  else box.append(el('span', { class: 'muted small' }, 'No known rank.'));
  if (p.flat_progress != null) box.append(el('span', { class: 'small muted', title: 'Continuous rank progress after the last match (higher = better)' }, `Progress ${fmt.int(p.flat_progress)}`));
  const sp = sparkline(series.map(b => b.flat ?? b.badge), { w: 140, h: 28 });
  if (sp) box.append(sp);
  return box;
}

function closeBtn() {
  return el('button', { type: 'button', class: 'pf-close', 'aria-label': 'Close profile', onclick: () => closeDrawer() }, el('span', { 'aria-hidden': 'true' }, '✕'));
}

// ---- dialog: focus, Esc, clickable backdrop
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
  // focus trap inside the dialog
  const f = [...d.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')].filter(x => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (!d.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

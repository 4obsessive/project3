import { api, getHeroes } from '../api.js';
import { el, dataTable, toast, spinner, store, errorBox, headline } from '../util.js';
import { renderSection, setLanes, setHeroes } from '../blocks.js';
import { heroPortrait } from '../art.js';

export async function render(root, ctx) {
  const teams = await api.get('/api/teams');
  const saved = store.get('report', { team: '', extra: '', ids: '', window: 90, normalize: true });
  if (ctx.query.team) saved.team = ctx.query.team;
  const teamSel = el('select', {}, el('option', { value: '' }, '— extra accounts only —'), teams.map(t => el('option', { value: t.team, selected: t.team === saved.team }, `${t.team} (${t.players.length})`)));
  const extra = el('input', { value: saved.extra, placeholder: 'extra accounts, comma separated', style: { minWidth: '280px' } });
  const ids = el('textarea', { 'aria-label': 'Match IDs', placeholder: 'Match IDs (one per line or comma separated)' }, saved.ids);
  const win = el('input', { type: 'number', value: saved.window, min: 10, max: 600, style: { width: '70px' } });
  const norm = el('input', { type: 'checkbox', checked: saved.normalize });
  const minP = el('input', { type: 'number', value: 3, min: 1, max: 6, style: { width: '50px' } });
  const days = el('input', { type: 'number', value: 60, min: 1, max: 365, style: { width: '60px' } });
  const recentBox = el('div');
  const out = el('div');
  let overrides = {};

  const parseIds = () => [...new Set(ids.value.split(/[\s,;]+/).map(x => x.trim()).filter(x => /^\d+$/.test(x)))];
  const persist = () => store.set('report', { team: teamSel.value, extra: extra.value, ids: ids.value, window: +win.value, normalize: norm.checked });

  async function findRecent() {
    recentBox.innerHTML = ''; recentBox.append(spinner('Searching the roster\'s match history…'));
    try {
      const q = new URLSearchParams({ team: teamSel.value, extra: extra.value, min_players: minP.value, days: days.value });
      const r = await api.get('/api/teams/recent-matches?' + q);
      recentBox.innerHTML = '';
      const chosen = new Set(parseIds());
      recentBox.append(el('div', { class: 'muted small' }, `${r.matches.length} matches with ≥${minP.value} roster accounts (${r.roster_accounts} accounts) on the same team` + (r.errors.length ? ` · ${r.errors.length} accounts without history` : '')),
        el('div', { class: 'row' },
          el('button', { onclick: () => { ids.value = r.matches.map(m => m.match_id).join('\n'); persist(); toast(`${r.matches.length} matches added`); } }, 'Use all'),
          el('button', { onclick: () => { ids.value = r.matches.slice(0, 20).map(m => m.match_id).join('\n'); persist(); } }, 'Use the 20 most recent')),
        dataTable([
          { key: 'add', label: '', sortable: false, render: m => { const c = el('input', { type: 'checkbox', 'aria-label': `Use match ${m.match_id}`, checked: chosen.has(String(m.match_id)) }); c.addEventListener('change', () => { const s = new Set(parseIds()); c.checked ? s.add(String(m.match_id)) : s.delete(String(m.match_id)); ids.value = [...s].join('\n'); persist(); }); return c; } },
          { key: 'match_id', label: 'Match' }, { key: 'start_time', label: 'Date', fmt: 'date' }, { key: 'duration_s', label: 'Length', fmt: 'mmss' },
          { key: 'side', label: 'Side', render: m => el('span', { class: `tag t${m.side}` }, ctx.teamNames[m.side]) },
          { key: 'roster_players', label: 'From the roster' }, { key: 'won', label: 'Result', render: m => m.won ? 'Win' : 'Loss' },
          { key: 'stored', label: 'Stored', render: m => m.stored ? 'yes' : '' },
        ], r.matches, { sortKey: 'start_time', maxHeight: '300px' }));
    } catch (e) { recentBox.innerHTML = ''; recentBox.append(errorBox(e.message, findRecent, 'Could not search for matches')); }
  }

  async function run() {
    persist();
    const list = parseIds();
    if (!list.length) return toast('Enter at least one match', true);
    out.innerHTML = ''; out.append(spinner(`Analysing ${list.length} matches (the ones not stored are downloaded)…`));
    try {
      const r = await api.post('/api/report', {
        team: teamSel.value, extra_accounts: extra.value.split(/[\s,;]+/).filter(Boolean), match_ids: list, side_overrides: overrides,
        params: { midboss_window_s: +win.value, normalize: norm.checked },
      });
      await show(r);
    } catch (e) { out.innerHTML = ''; out.append(errorBox(e.message, run, 'Could not generate the report')); }
  }

  function heroStrip(r, byId) {
    if (!(r.our_heroes || []).length) return null;
    return el('div', { class: 'report-heroes tilt-cards', role: 'group', 'aria-label': 'Team heroes in the analysed matches' },
      r.our_heroes.map(o => {
        const h = byId.get(o.hero_id) || { id: o.hero_id, name: `#${o.hero_id}` };
        return el('span', { title: `${h.name}: ${o.matches} ${o.matches === 1 ? 'match' : 'matches'}` },
          heroPortrait(h, { size: 'md', shape: 'card' }), el('b', {}, `×${o.matches}`));
      }));
  }

  async function show(r) {
    // catálogo de héroes para los retratos de las tablas y tarjetas (sin él: iniciales)
    let heroes = [];
    try { heroes = await getHeroes(); } catch (e) { /* sin catálogo: se muestran las iniciales */ }
    setHeroes(heroes);
    const byId = new Map(heroes.map(h => [h.id, h]));
    out.innerHTML = '';
    setLanes(r.lanes);
    const TN = r.team_names;
    const head = el('div', { class: 'panel' },
      headline('Report: ', r.team || 'extra accounts'),
      el('div', { class: 'muted' }, `${r.n} matches analysed · roster of ${r.roster_size} accounts · Midboss window ${r.params.midboss_window_s} s · ${r.params.normalize ? 'side normalized' : 'not normalized'}`),
      heroStrip(r, byId),
      r.team_names_verified ? null : el('div', { class: 'muted small' }, 'Side names (team 0 = Hidden King, 1 = Archmother) come from third-party sources; that team 0 has its base at the bottom is verified.'),
      r.load_errors.length ? el('div', { class: 'note warning block' }, el('span', { class: 'lbl' }, 'warning'), 'Could not load: ' + r.load_errors.map(e => `${e.match_id} (${e.error})`).join(' · ')) : null);
    // lados detectados con corrección manual
    const sideRows = r.sides.map(s => ({ ...s }));
    head.append(el('details', { open: r.skipped.length > 0 }, el('summary', {}, `Side per match (${r.skipped.length} not detected)`),
      dataTable([
        { key: 'match_id', label: 'Match' },
        { key: 'counts', label: 'Roster on 0 / 1', render: s => `${s.roster_counts[0]} / ${s.roster_counts[1]}` },
        { key: 'auto', label: 'Detected', render: s => s.auto == null ? '—' : TN[s.auto] },
        { key: 'side', label: 'Used', render: s => {
          const sel = el('select', { 'aria-label': `Side of match ${s.match_id}` }, el('option', { value: '' }, 'auto'), [0, 1].map(t => el('option', { value: t, selected: s.source === 'manual' && s.side === t }, TN[t])));
          sel.addEventListener('change', () => { if (sel.value === '') delete overrides[s.match_id]; else overrides[s.match_id] = +sel.value; });
          return sel;
        } },
      ], sideRows),
      el('button', { onclick: run }, 'Recalculate with these sides')));
    const toc = el('nav', { class: 'toc no-print', 'aria-label': 'Report contents' }, el('ol', {}, r.sections.map(s => el('li', {}, el('button', { type: 'button', class: 'linkbtn', onclick: () => { const t = document.getElementById('sec-' + s.id); if (t) { t.tabIndex = -1; t.scrollIntoView({ behavior: 'smooth' }); t.focus({ preventScroll: true }); } } }, s.title)))));
    head.append(toc, el('button', { class: 'no-print', onclick: () => window.print() }, 'Print / PDF'));
    out.append(head, ...r.sections.map(renderSection));
  }

  root.append(el('div', { class: 'panel no-print' },
    el('h3', {}, 'Team statistical report'),
    el('p', { class: 'muted small' }, 'Analyses N matches together. The side of each match is detected from which roster players are on each team; it can be corrected by hand. What the API does not provide is marked as «not available».'),
    el('div', { class: 'row' }, el('label', {}, 'Team', teamSel), el('label', {}, 'Extra accounts', extra)),
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { onclick: findRecent }, 'Find recent team matches'),
      el('label', {}, 'min. players together', minP), el('label', {}, 'last', days, 'days')),
    recentBox,
    el('div', { style: { marginTop: '8px' } }, ids),
    el('div', { class: 'row', style: { marginTop: '8px' } },
      el('label', {}, 'Kill window before the Midboss (s)', win),
      el('label', {}, norm, 'normalize side (own base at the bottom)'),
      el('button', { class: 'primary', onclick: () => { overrides = {}; run(); } }, 'Generate report'))), out);
}

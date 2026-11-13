import { api, getPlayers, getHeroes } from '../api.js';
import { el, fmt, store, errorBox } from '../util.js';
import { sectionHead, emptyState, deltaChip, sparkline, rankEmblem, getRanks, skeleton, playerPic, cellBar } from '../ui.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  let days = store.get('climbDays', 7), metric = store.get('climbMetric', 'rel');
  const seg = (opts, cur, set) => el('div', { class: 'segmented', role: 'group' }, opts.map(([v, l]) => el('button', { type: 'button', class: 'seg' + (v === cur() ? ' active' : ''), 'aria-pressed': String(v === cur()),
    onclick: e => { set(v); for (const b of e.currentTarget.parentNode.children) { const on = b === e.currentTarget; b.classList.toggle('active', on); b.setAttribute('aria-pressed', String(on)); } load(); } }, l)));
  const head = el('div', { class: 'filterbar' },
    seg([[7, '7 days'], [30, '30 days']], () => days, v => { days = v; store.set('climbDays', v); }),
    seg([['rel', 'Relative'], ['pos', 'Positions'], ['mmr', 'MMR']], () => metric, v => { metric = v; store.set('climbMetric', v); }));
  const chips = el('div', { class: 'list-meta' });
  const body = el('div');
  root.append(head, chips, body);

  async function load() {
    body.replaceChildren(skeleton('rows'));
    let c, players, ranks, heroes;
    try { [c, players, ranks, heroes] = await Promise.all([api.get(`/api/climbers?days=${days}&metric=${metric === 'pos' ? 'pos' : 'rel'}`), getPlayers(), getRanks(), getHeroes().catch(() => [])]); }
    catch (e) { body.replaceChildren(errorBox(e.message, load)); return; }
    const by = Object.fromEntries(players.map(p => [p.id, p]));
    const heroById = new Map(heroes.map(h => [h.id, h]));
    const heroOf = p => p?.heroes?.[0] && (heroById.get(p.heroes[0].hero_id) || { name: p.heroes[0].name });
    const nm = r => (by[r.player_id]?.name) || r.name || '—';
    chips.replaceChildren(
      c.base_taken_at ? el('span', { class: 'chip' }, `${fmt.datetime(c.base_taken_at)} → ${fmt.datetime(c.latest_taken_at)} · ${c.snapshots} snapshots`) : null,
      c.size_warning ? el('span', { class: 'chip warn', title: c.size_warning }, `Size ${c.base_entries} → ${c.latest_entries}`) : null);
    body.innerHTML = '';
    if (c.warning) body.append(el('div', { class: 'note warning block' }, c.warning));
    if (c.size_warning) body.append(el('div', { class: 'note warning block' }, c.size_warning));
    const row = (r, right, ft) => el('div', { class: 'crow' },
      el('button', { type: 'button', class: 'linkbtn pl-cell', onclick: () => openProfile(r.player_id, ctx) }, playerPic(by[r.player_id], heroOf(by[r.player_id]), { size: 'mini' }), el('span', { class: 'nm' }, nm(r))), el('span', { class: 'ft' }, ft), right);
    const col = (title, items, fn, empty) => el('div', { class: 'panel' }, sectionHead(`${title} (${items.length})`),
      items.length ? items.slice(0, 25).map(fn) : emptyState(empty));
    const maxOf = (items, get) => Math.max(1e-9, ...items.map(x => Math.abs(get(x) || 0)));
    if (metric === 'mmr') {
      const up = c.badge_climbers.filter(x => x.delta > 0), down = c.badge_climbers.filter(x => x.delta < 0).reverse();
      const maxD = maxOf(c.badge_climbers, x => x.delta);
      const f = x => row(x, el('span', { class: 'row' }, sparkline(x.points, { w: 60, h: 18 }), deltaChip(x.delta, { fmtFn: v => fmt.signed0(v) }), cellBar(x.delta, maxD, '')),
        el('span', {}, rankEmblem(x.to_badge, ranks, { label: false })));
      body.append(el('div', { class: 'climb-cols' }, col('Climbing', up, f, 'Two updates with rank data are needed to measure climbs.'),
        col('No change', c.badge_climbers.filter(x => !x.delta), x => row(x, el('span'), ''), '—'), col('Falling', down, f, 'Nobody is falling.')));
      return;
    }
    const mval = r => metric === 'pos' ? r.delta : r.rel;
    const maxV = maxOf([...c.climbers, ...c.fallers], mval);
    const mv = r => el('span', { class: 'row' }, deltaChip(mval(r), { fmtFn: v => metric === 'pos' ? fmt.signed0(v) : `×${(2 ** Math.abs(v)).toFixed(2)}` }), cellBar(mval(r), maxV, ''));
    body.append(el('div', { class: 'climb-cols' },
      col('Climbing', c.climbers, r => row(r, mv(r), `#${r.from} → #${r.to}`), 'Nobody climbed in this period.'),
      col('New entries', c.new, r => row(r, el('span'), `#${r.rank}`), 'No new entries.'),
      col('Falling / dropped', [...c.fallers, ...c.dropped], r => row(r, r.to ? mv(r) : el('span', { class: 'delta down' }, 'dropped'), r.to ? `#${r.from} → #${r.to}` : `#${r.from} → out`), 'Nobody is falling.')));
  }
  load();
}

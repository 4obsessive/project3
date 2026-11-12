import { api, getPlayers } from '../api.js';
import { el, fmt, store, errorBox } from '../util.js';
import { sectionHead, emptyState, deltaChip, sparkline, rankEmblem, getRanks, skeleton } from '../ui.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  let days = store.get('climbDays', 7), metric = store.get('climbMetric', 'rel');
  const seg = (opts, cur, set) => el('div', { class: 'segmented', role: 'group' }, opts.map(([v, l]) => el('button', { type: 'button', class: 'seg' + (v === cur() ? ' active' : ''), 'aria-pressed': String(v === cur()),
    onclick: e => { set(v); for (const b of e.currentTarget.parentNode.children) { const on = b === e.currentTarget; b.classList.toggle('active', on); b.setAttribute('aria-pressed', String(on)); } load(); } }, l)));
  const head = el('div', { class: 'filterbar' },
    seg([[7, '7 días'], [30, '30 días']], () => days, v => { days = v; store.set('climbDays', v); }),
    seg([['rel', 'Relativo'], ['pos', 'Posiciones'], ['mmr', 'MMR']], () => metric, v => { metric = v; store.set('climbMetric', v); }));
  const chips = el('div', { class: 'list-meta' });
  const body = el('div');
  root.append(head, chips, body);

  async function load() {
    body.replaceChildren(skeleton('rows'));
    let c, players, ranks;
    try { [c, players, ranks] = await Promise.all([api.get(`/api/climbers?days=${days}&metric=${metric === 'pos' ? 'pos' : 'rel'}`), getPlayers(), getRanks()]); }
    catch (e) { body.replaceChildren(errorBox(e.message, load)); return; }
    const by = Object.fromEntries(players.map(p => [p.id, p]));
    const nm = r => (by[r.player_id]?.name) || r.name || '—';
    chips.replaceChildren(
      c.base_taken_at ? el('span', { class: 'chip' }, `${fmt.datetime(c.base_taken_at)} → ${fmt.datetime(c.latest_taken_at)} · ${c.snapshots} snapshots`) : null,
      c.size_warning ? el('span', { class: 'chip warn', title: c.size_warning }, `Tamaño ${c.base_entries} → ${c.latest_entries}`) : null);
    body.innerHTML = '';
    if (c.warning) body.append(el('div', { class: 'note warning block' }, c.warning));
    if (c.size_warning) body.append(el('div', { class: 'note warning block' }, c.size_warning));
    const row = (r, right, ft) => el('div', { class: 'crow' },
      el('button', { type: 'button', class: 'linkbtn', onclick: () => openProfile(r.player_id, ctx) }, nm(r)), el('span', { class: 'ft' }, ft), right);
    const col = (title, items, fn, empty) => el('div', { class: 'panel' }, sectionHead(`${title} (${items.length})`),
      items.length ? items.slice(0, 25).map(fn) : emptyState(empty));
    if (metric === 'mmr') {
      const up = c.badge_climbers.filter(x => x.delta > 0), down = c.badge_climbers.filter(x => x.delta < 0).reverse();
      const f = x => row(x, el('span', { class: 'row' }, sparkline(x.points, { w: 60, h: 18 }), deltaChip(x.delta, { fmtFn: v => fmt.signed0(v) })),
        el('span', {}, rankEmblem(x.to_badge, ranks, { label: false })));
      body.append(el('div', { class: 'climb-cols' }, col('Suben', up, f, 'Hacen falta dos actualizaciones con rango para medir subidas.'),
        col('Sin cambios', c.badge_climbers.filter(x => !x.delta), x => row(x, el('span'), ''), '—'), col('Bajan', down, f, 'Nadie baja.')));
      return;
    }
    const mv = r => deltaChip(metric === 'pos' ? r.delta : r.rel, { fmtFn: v => metric === 'pos' ? fmt.signed0(v) : `×${(2 ** Math.abs(v)).toFixed(2)}` });
    body.append(el('div', { class: 'climb-cols' },
      col('Suben', c.climbers, r => row(r, mv(r), `#${r.from} → #${r.to}`), 'Nadie sube en este periodo.'),
      col('Nuevos', c.new, r => row(r, el('span'), `#${r.rank}`), 'Sin entradas nuevas.'),
      col('Bajan / salen', [...c.fallers, ...c.dropped], r => row(r, r.to ? mv(r) : el('span', { class: 'delta down' }, 'sale'), r.to ? `#${r.from} → #${r.to}` : `#${r.from} → fuera`), 'Nadie baja.')));
  }
  load();
}

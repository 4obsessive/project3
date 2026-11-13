// Shared visual components (no dependencies): hero art, rank, score, winrate,
// confidence, roles, form, sparkline, tiles, skeletons, tabs and empty states.
import { el, fmt } from './util.js';
import { api } from './api.js';
import { icon } from './icons.js';

const NS = 'http://www.w3.org/2000/svg';
function s(tag, attrs = {}, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  for (const k of kids) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}

export const ROLE_VAR = {
  carry: '--role-carry', 'off-carry': '--role-offcarry', offcarry: '--role-offcarry', initiator: '--role-initiator',
  frontline: '--role-frontline', catcher: '--role-catcher', support: '--role-support',
};
export const roleColor = r => `var(${ROLE_VAR[String(r || '').toLowerCase()] || '--text-3'})`;

// ------------------------------------------------------------- rangos
let ranksCache = null;
export async function getRanks() {
  if (!ranksCache) ranksCache = api.get('/api/ranks').catch(() => []);
  return ranksCache;
}
export function badgeName(badge, ranks) {
  if (!badge) return null;
  const tier = Math.floor(badge / 10), sub = badge % 10;
  const r = (ranks || []).find(x => x.tier === tier);
  return r ? `${r.name}${sub ? ' ' + sub : ''}` : `Badge ${badge}`;
}

/** Emblema de rango: imagen del subrango (por /img/api/) + nombre; si no hay imagen, solo texto. */
export function rankEmblem(badge, ranks, { size = 'sm', label = true } = {}) {
  if (!badge) return el('span', { class: 'rank-emblem none muted' }, '—');
  const tier = Math.floor(badge / 10), sub = badge % 10;
  const r = (ranks || []).find(x => x.tier === tier);
  const name = badgeName(badge, ranks);
  const src = r && (r.subranks?.[String(sub)] || r.image);
  const box = el('span', { class: `rank-emblem ${size}`, title: name });
  if (src) {
    const img = el('img', { src, alt: label ? '' : name, loading: 'lazy' });
    img.addEventListener('error', () => img.remove());
    box.append(img);
  }
  if (label) box.append(el('span', { class: 'rank-name' }, name));
  return box;
}

// ------------------------------------------------------------- héroes
/** Arte de héroe: card (cubre) con scrim inferior tintado por el color del héroe. */
export function heroArt(hero, { size = 'card', label = false, decorative = true, kind = 'card' } = {}) {
  hero = hero || {};
  const chain = (kind === 'bg' ? [hero.bg, hero.card, hero.vertical] : kind === 'vertical' ? [hero.vertical, hero.card] : [hero.card, hero.vertical, hero.image])
    .concat([hero.wiki_image]).filter(Boolean);
  const box = el('span', { class: `hero-art ${size}`, style: hero.color ? { '--hero': hero.color } : null,
    ...(decorative ? { 'aria-hidden': 'true' } : { role: 'img', 'aria-label': hero.name || '' }) });
  if (chain.length) {
    let i = 0;
    const img = el('img', { src: chain[0], alt: '', loading: 'lazy' });
    img.addEventListener('error', () => { i += 1; if (i < chain.length) img.src = chain[i]; else img.remove(); });
    box.append(img);
  } else box.append(el('span', { class: 'hero-art-initial' }, (hero.name || '?')[0]));
  if (label) box.append(el('span', { class: 'hero-art-name' }, hero.name));
  return box;
}

// ------------------------------------------------------------- score
/** Anillo de score con banda lo–hi; dorado si ≥ 85. */
export function scoreRing(score, { lo = null, hi = null, size = 40, provisional = false } = {}) {
  if (score == null) return el('span', { class: 'muted' }, '–');
  const r = size / 2 - 3.5, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score));
  const svg = s('svg', { viewBox: `0 0 ${size} ${size}`, width: size, height: size, 'aria-hidden': 'true' });
  const arc = (from, to, cls) => s('circle', { cx: size / 2, cy: size / 2, r, class: cls, 'stroke-dasharray': `${c * (to - from) / 100} ${c}`,
    'stroke-dashoffset': -c * from / 100, transform: `rotate(-90 ${size / 2} ${size / 2})` });
  svg.append(s('circle', { cx: size / 2, cy: size / 2, r, class: 'ring-track' }));
  if (lo != null && hi != null) svg.append(arc(Math.max(0, lo), Math.min(100, hi), 'ring-band'));
  svg.append(arc(0, v, 'ring-val'));
  const tip = `Score ${Math.round(v)} of 100` + (lo != null ? ` · band ${Math.round(lo)}–${Math.round(hi)}` : '') + (provisional ? ' · provisional (<20 matches)' : '');
  return el('span', { class: `score-ring s${size}` + (v >= 85 ? ' gold' : '') + (provisional ? ' prov' : ''), title: tip, role: 'img', 'aria-label': tip },
    svg, el('span', { class: 'score-num' }, Math.round(v)));
}

// ------------------------------------------------------------- winrate
/** Número + micro-barra de 48 px con marca al 50 % y bigote del intervalo. */
export function wrBar(wr, { lo = null, hi = null, muted = false, n = null } = {}) {
  if (wr == null) return el('span', { class: 'muted' }, '–');
  const pct = x => Math.max(0, Math.min(100, x * 100)) + '%';
  const tone = muted ? 'muted' : wr >= 0.55 ? 'good' : wr <= 0.45 ? 'bad' : 'mid';
  const tip = `${fmt.pct(wr)}${n != null ? ` in ${fmt.int(n)} matches` : ''}${lo != null ? ` · 95% CI ${fmt.pct(lo)}–${fmt.pct(hi)}` : ''}`;
  return el('span', { class: `wrbar ${tone}`, title: tip },
    el('span', { class: 'wr-num' }, fmt.pct(wr)),
    el('span', { class: 'wr-track', 'aria-hidden': 'true' },
      lo != null ? el('span', { class: 'wr-ci', style: { left: pct(lo), width: `calc(${pct(hi)} - ${pct(lo)})` } }) : null,
      el('span', { class: 'wr-mid' }),
      el('span', { class: 'wr-dot', style: { left: pct(wr) } })));
}

const LEVELS = ['Insufficient', 'Low', 'Medium', 'High'];
/** Four segments (Insufficient/Low/Medium/High) with tooltip "68% in 466 matches · 95% CI 64–72%". */
export function confidencePips(level, { wr = null, n = null, lo = null, hi = null } = {}) {
  const k = Math.max(0, LEVELS.indexOf(level));
  const tip = `Confidence: ${String(level || 'Insufficient').toLowerCase()}` +
    (n != null ? ` · ${wr != null ? fmt.pct(wr) + ' in ' : ''}${fmt.int(n)} matches` : '') +
    (lo != null ? ` · 95% CI ${Math.round(lo * 100)}–${Math.round(hi * 100)}%` : '');
  return el('span', { class: `pips l${k}`, title: tip, role: 'img', 'aria-label': tip },
    [0, 1, 2, 3].map(i => el('i', { class: i <= k && k > 0 ? 'on' : '' })));
}

// ------------------------------------------------------------- roles
/** At most two chips (colour dot + role + %), "+N" with the full split in the tooltip. */
export function roleChips(p, { max = 2 } = {}) {
  const br = (p.role_breakdown || []).filter(([r]) => r !== 'No role');
  if (!br.length) return el('span', { class: 'muted small' }, p.role_text === 'insufficient sample' ? 'insufficient sample' : '–');
  const full = br.map(([r, v]) => `${r} ${Math.round(v * 100)}%`).join(' · ');
  const shown = br.slice(0, max);
  return el('span', { class: 'role-chips', title: full },
    shown.map(([r, v]) => el('span', { class: 'role-chip', style: { '--role': roleColor(r) } }, el('i', { 'aria-hidden': 'true' }), r, el('b', {}, Math.round(v * 100) + '%'))),
    br.length > max ? el('span', { class: 'role-more' }, `+${br.length - max}`) : null);
}

/** Single stacked bar with the role split. */
export function roleStack(p) {
  const br = (p.role_breakdown || []).filter(([, v]) => v >= 0.01);
  if (!br.length) return el('p', { class: 'muted small' }, p.role_text === 'insufficient sample' ? 'Not enough matches to assign roles (fewer than 10).' : 'No role data.');
  return el('div', { class: 'role-stack-wrap' },
    el('div', { class: 'role-stack', role: 'img', 'aria-label': 'Role split: ' + br.map(([r, v]) => `${r} ${Math.round(v * 100)}%`).join(', ') },
      br.map(([r, v]) => el('span', { style: { width: (v * 100) + '%', background: roleColor(r) }, title: `${r} ${Math.round(v * 100)}%` }))),
    el('div', { class: 'role-legend' }, br.map(([r, v]) => el('span', { class: 'role-chip', style: { '--role': roleColor(r) } }, el('i'), r, el('b', {}, Math.round(v * 100) + '%')))));
}

// ------------------------------------------------------------- forma
export function formStrip(last20) {
  if (!last20?.length) return el('span', { class: 'muted small' }, '–');
  const items = last20.slice().reverse();
  const w = items.filter(x => x.won).length;
  return el('span', { class: 'form-strip', role: 'img', 'aria-label': `Last ${items.length}: ${w} wins, ${items.length - w} losses` },
    items.map(x => el('i', { class: x.won ? 'w' : 'l' })));
}

export function deltaChip(v, { fmtFn = x => fmt.signed(x * 100, 0) + ' pp', title = null } = {}) {
  if (v == null || !isFinite(v)) return el('span', { class: 'muted' }, '–');
  const cls = v > 0.005 ? 'up' : v < -0.005 ? 'down' : 'flat';
  return el('span', { class: `delta ${cls}`, title }, el('span', { 'aria-hidden': 'true' }, cls === 'up' ? '▲' : cls === 'down' ? '▼' : '■'), ' ', fmtFn(v));
}

export function sparkline(values, { w = 80, h = 24, cls = '' } = {}) {
  const v = (values || []).filter(x => x != null && isFinite(x));
  if (v.length < 2) return null;
  const mn = Math.min(...v), mx = Math.max(...v), rg = mx - mn || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * (w - 2) + 1},${h - 2 - ((x - mn) / rg) * (h - 4)}`).join(' ');
  return s('svg', { class: 'spark ' + cls, viewBox: `0 0 ${w} ${h}`, width: w, height: h, 'aria-hidden': 'true' },
    s('polyline', { points: pts }));
}

// ------------------------------------------------------------- tiles y estructura
export function statTile(label, value, { sub = null, art = null, spark = null, onClick = null, extra = null, tone = '' } = {}) {
  const tag = onClick ? 'button' : 'div';
  return el(tag, { class: 'stat-tile ' + tone, ...(onClick ? { type: 'button', onclick: onClick } : {}) },
    art ? el('span', { class: 'tile-art', 'aria-hidden': 'true' }, art) : null,
    el('span', { class: 'tile-label' }, label),
    el('span', { class: 'tile-value' }, value),
    sub ? el('span', { class: 'tile-sub' }, sub) : null,
    extra, spark);
}

export function sectionHead(label, ...right) {
  return el('div', { class: 'sec-head' }, el('h2', { class: 'sec-label' }, label), el('span', { class: 'spacer' }), ...right);
}

export function emptyState(text, { ico = 'grid', action = null } = {}) {
  return el('div', { class: 'empty-state' }, icon(ico, 'big'), el('p', {}, text), action);
}

/** Skeleton con la forma de la vista final (sustituye a los spinners de carga de ruta). */
export function skeleton(kind = 'table') {
  const bar = (cls = '') => el('span', { class: 'sk ' + cls });
  const box = el('div', { class: 'skeleton', role: 'status', 'aria-label': 'Loading…' }, el('span', { class: 'sr-only' }, 'Loading…'));
  if (kind === 'tiles' || kind === 'table') box.append(el('div', { class: 'sk-tiles' }, [0, 1, 2, 3].map(() => bar('tile'))));
  if (kind === 'table' || kind === 'rows') box.append(el('div', { class: 'sk-rows' }, Array.from({ length: 8 }, () => bar('row'))));
  if (kind === 'grid') box.append(el('div', { class: 'sk-grid' }, Array.from({ length: 6 }, () => bar('card'))));
  if (kind === 'drawer') box.append(bar('banner'), el('div', { class: 'sk-tiles' }, [0, 1, 2, 3].map(() => bar('tile'))), el('div', { class: 'sk-rows' }, Array.from({ length: 5 }, () => bar('row'))));
  return box;
}

/** Pestañas accesibles (role=tablist, flechas izquierda/derecha) con subrayado deslizante. */
export function tabs(items, { onChange, initial = 0, label = 'Sections' } = {}) {
  const list = el('div', { class: 'tabs v3', role: 'tablist', 'aria-label': label });
  const ink = el('span', { class: 'tab-ink', 'aria-hidden': 'true' });
  const btns = items.map((it, i) => el('button', { type: 'button', role: 'tab', id: `tab-${it.id}`, 'aria-selected': String(i === initial), tabindex: i === initial ? '0' : '-1',
    onclick: () => select(i) }, it.label));
  list.append(...btns, ink);
  function place(i) {
    const b = btns[i];
    if (!b.offsetWidth) return;
    ink.style.width = b.offsetWidth + 'px';
    ink.style.transform = `translateX(${b.offsetLeft}px)`;
  }
  function select(i, focus = true) {
    btns.forEach((b, j) => { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; b.classList.toggle('active', i === j); });
    if (focus) btns[i].focus();
    place(i);
    onChange?.(items[i].id, i);
  }
  list.addEventListener('keydown', e => {
    const cur = btns.findIndex(b => b.getAttribute('aria-selected') === 'true');
    if (e.key === 'ArrowRight') { e.preventDefault(); select((cur + 1) % btns.length); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); select((cur - 1 + btns.length) % btns.length); }
  });
  btns[initial].classList.add('active');
  requestAnimationFrame(() => place(initial));
  window.addEventListener('resize', () => place(Math.max(0, btns.findIndex(b => b.classList.contains('active')))));
  list.select = select;
  return list;
}

const reduce = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
/** Cuenta hacia arriba una vez (≤ 400 ms) al primer pintado. */
export function countUp(node, target, format = v => Math.round(v)) {
  if (reduce() || target == null || !isFinite(target)) { node.textContent = format(target); return node; }
  const t0 = performance.now(), dur = 400;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur);
    node.textContent = format(target * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  return node;
}

/** "Ranked · Oct 12 – Nov 12 · 466 matches" */
export function windowText(win, n = null) {
  if (!win) return '';
  const mode = win.match_mode === 'ranked' ? 'Ranked' : win.match_mode ? 'Ranked + normal' : 'All matches';
  const d = t => new Date(t * 1000).toLocaleDateString('en-US', { day: 'numeric', month: 'short' }).replace('.', '');
  const range = win.start && win.end ? `${d(win.start)} – ${d(win.end)}` : '';
  return [mode, range, n != null ? `${fmt.int(n)} matches` : null].filter(Boolean).join(' · ');
}

/** Number with a small in-cell bar (0..max); `compact` for dense ranking tables. */
export function cellBar(value, max, text, { compact = true, title = null } = {}) {
  if (value == null || !isFinite(value)) return el('span', { class: 'muted' }, '–');
  const pct = !max ? 0 : Math.max(0, Math.min(100, 100 * Math.abs(value) / max));
  return el('span', { class: 'cell-bar' + (compact ? ' compact' : '') + (value < 0 ? ' neg' : ''), title },
    el('span', { class: 'cell-bar-track', 'aria-hidden': 'true' }, el('span', { class: 'cell-bar-fill', style: { width: pct + '%' } })),
    el('span', { class: 'cell-bar-val' }, text ?? fmt.int(value)));
}

/** Round avatar of a player: Steam avatar, falling back to the hero art (or an initial). */
export function playerPic(p, hero, { size = 'round' } = {}) {
  const fallback = () => heroArt(hero || { name: p?.name }, { size });
  if (!p?.avatar) return fallback();
  const img = el('img', { class: 'avatar-img', src: p.avatar, alt: '', loading: 'lazy' });
  img.addEventListener('error', () => img.replaceWith(fallback()));
  return img;
}

// Tracking statuses and the adult flag are stored as fixed values; these are their English labels.
export const STATUS_LABEL = { pendiente: 'Pending', 'en seguimiento': 'Tracking', contactado: 'Contacted', 'en prueba': 'On trial', fichado: 'Signed', descartado: 'Dropped' };
export const ADULT_LABEL = { desconocido: 'Unknown', 'sí': 'Yes', no: 'No' };

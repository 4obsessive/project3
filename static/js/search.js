// Global search (/ or Ctrl+K): players, heroes and match IDs. Accessible combobox.
import { el } from './util.js';
import { getPlayers, getHeroes } from './api.js';
import { icon } from './icons.js';
import { heroArt } from './ui.js';

export function initSearch(box, ctx) {
  const input = el('input', { type: 'search', placeholder: 'Search player, hero or match…', 'aria-label': 'Global search',
    role: 'combobox', 'aria-expanded': 'false', 'aria-controls': 'gs-list', 'aria-autocomplete': 'list', autocomplete: 'off' });
  const list = el('ul', { class: 'gs-results', id: 'gs-list', role: 'listbox', hidden: true });
  box.append(icon('filter'), input, el('kbd', { 'aria-hidden': 'true' }, '/'), list);
  let items = [], sel = -1;

  async function results(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    const out = [];
    if (/^\d{6,}$/.test(q)) out.push({ kind: 'Match', label: `Match ${q}`, go: () => { location.hash = `#matches/${q}`; } });
    const [players, heroes] = await Promise.all([getPlayers().catch(() => []), getHeroes().catch(() => [])]);
    for (const h of heroes) if (h.name.toLowerCase().includes(q)) out.push({ kind: 'Hero', label: h.name, hero: h, go: () => { location.hash = `#hero/${h.id}`; } });
    const ps = players.filter(p => p.name.toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q) || p.accounts.some(a => String(a.account_id) === q))
      .sort((a, b) => (b.score_default ?? -1) - (a.score_default ?? -1)).slice(0, 8);
    for (const p of ps) out.push({ kind: p.team || 'Player', label: p.name, player: p,
      go: async () => { const { openProfile } = await import('./views/profile.js'); openProfile(p.id, ctx); } });
    return out.slice(0, 12);
  }
  function paint() {
    list.innerHTML = '';
    items.forEach((it, i) => {
      const li = el('li', { role: 'option', id: `gs-${i}`, 'aria-selected': String(i === sel), onclick: () => choose(i) },
        it.hero ? heroArt(it.hero, { size: 'mini' }) : it.player?.avatar ? el('img', { class: 'avatar-img', src: it.player.avatar, alt: '', style: { width: '22px', height: '22px' } }) : icon(it.kind === 'Match' ? 'matches' : 'players'),
        el('span', {}, it.label), el('span', { class: 'gs-kind' }, it.kind));
      list.append(li);
    });
    if (!items.length && input.value.trim()) list.append(el('li', { class: 'gs-empty', role: 'option', 'aria-disabled': 'true' }, 'No results'));
    const open = !!input.value.trim();
    list.hidden = !open;
    input.setAttribute('aria-expanded', String(open));
    if (sel >= 0) input.setAttribute('aria-activedescendant', `gs-${sel}`); else input.removeAttribute('aria-activedescendant');
  }
  function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); sel = -1; }
  function choose(i) { const it = items[i]; if (!it) return; input.value = ''; close(); input.blur(); it.go(); }
  let seq = 0;
  input.addEventListener('input', async () => { const my = ++seq; const r = await results(input.value); if (my !== seq) return; items = r; sel = r.length ? 0 : -1; paint(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(items.length - 1, sel + 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); paint(); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(sel); }
    else if (e.key === 'Escape') { input.value = ''; close(); }
  });
  input.addEventListener('blur', () => setTimeout(close, 150));
  document.addEventListener('keydown', e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '') || document.activeElement?.isContentEditable;
    if ((e.key === '/' && !typing) || (e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey))) { e.preventDefault(); input.focus(); }
  });
}

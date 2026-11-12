import { api } from '../api.js';
import { el, fmt, dataTable, toast, spinner, csvDownload, store } from '../util.js';
import { MapView, COLORS, legend, loadMapInfo } from '../map.js';
import { timeline } from '../charts.js';
import { renderExplorer } from './explorer.js';
import { openProfile } from './profile.js';

export async function render(root, ctx) {
  const idInput = el('input', { placeholder: 'ID de partida', style: { width: '140px' } });
  const fileInput = el('input', { type: 'file', accept: '.json,application/json' });
  const list = el('div');
  const detail = el('div');
  const load = async () => {
    const id = idInput.value.trim();
    if (!id) return;
    btn.disabled = true; btn.textContent = 'Descargando…';
    try { await api.post('/api/matches/load', { match_id: id }); await refresh(); location.hash = `#partidas/${id}`; }
    catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; btn.textContent = 'Cargar'; }
  };
  const btn = el('button', { class: 'primary', onclick: load }, 'Cargar');
  idInput.addEventListener('keydown', e => { if (e.key === 'Enter') load(); });
  fileInput.addEventListener('change', async () => {
    const f = fileInput.files[0]; if (!f) return;
    try { const r = await api.post('/api/matches/upload', await f.text()); toast(`Partida ${r.match_id} guardada`); await refresh(); location.hash = `#partidas/${r.match_id}`; }
    catch (e) { toast(e.message, true); }
    fileInput.value = '';
  });
  root.append(el('div', { class: 'split' },
    el('div', {},
      el('div', { class: 'panel' }, el('h3', {}, 'Cargar partida'), el('div', { class: 'row' }, idInput, btn),
        el('div', { class: 'muted small', style: { margin: '8px 0 4px' } }, 'o subir su JSON (metadata de deadlock-api):'), fileInput),
      el('div', { class: 'panel' }, el('h3', {}, 'Guardadas'), list)),
    detail));

  async function refresh() {
    const ms = await api.get('/api/matches');
    list.innerHTML = '';
    if (!ms.length) list.append(el('div', { class: 'muted small' }, 'Ninguna todavía.'));
    for (const m of ms) {
      list.append(el('div', { class: 'row', style: { justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--line)' } },
        el('a', { href: `#partidas/${m.match_id}` }, m.match_id),
        el('span', { class: 'muted small' }, `${fmt.date(m.start_time)} · ${fmt.mmss(m.duration_s)}`)));
    }
  }
  await refresh();
  const id = ctx.params[0];
  if (id) showMatch(detail, id, ctx);
  else detail.append(el('div', { class: 'panel empty' }, 'Carga una partida por ID o sube su JSON.'));
}

async function showMatch(root, id, ctx) {
  root.innerHTML = ''; root.append(spinner('Cargando partida…'));
  let m;
  try { m = await api.get(`/api/matches/${id}`); } catch (e) { root.innerHTML = ''; root.append(el('div', { class: 'panel' }, e.message)); return; }
  root.innerHTML = '';
  const TN = m.team_names;
  const tname = t => `${TN[t]} (${t})`;
  const verified = m.team_names_verified ? '' : ' · nombres de lado según fuentes de terceros (equipo 0 = base abajo, verificado)';
  const head = el('div', { class: 'panel' },
    el('div', { class: 'row', style: { justifyContent: 'space-between' } },
      el('h2', {}, `Partida ${m.match_id}`),
      el('div', { class: 'row' },
        el('button', { onclick: async () => { if (!confirm('¿Borrar la partida guardada?')) return; await api.post(`/api/matches/${m.match_id}/delete`); location.hash = '#partidas'; } }, 'Borrar'))),
    el('div', { class: 'muted' }, `${fmt.datetime(m.start_time)} · ${fmt.mmss(m.duration_s)} · gana `, el('span', { class: `tag t${m.winning_team}` }, tname(m.winning_team)), el('span', { class: 'small' }, verified)));
  const tabs = el('div', { class: 'tabs' });
  const body = el('div', { class: 'panel' });
  root.append(head, tabs, body);
  const views = {
    'Resumen': () => resumen(body, m, tname, ctx),
    'Objetivos': () => objetivos(body, m, tname),
    'Midboss': () => midboss(body, m, tname),
    'Minimapa': () => minimapa(body, m, tname),
    'Explorador': () => renderExplorer(body, m.match_id),
  };
  let current = store.get('matchTab', 'Resumen');
  for (const name of Object.keys(views)) {
    const b = el('button', { class: name === current ? 'active' : '', onclick: () => { current = name; store.set('matchTab', name); [...tabs.children].forEach(x => x.classList.toggle('active', x === b)); body.innerHTML = ''; views[name](); } }, name);
    tabs.append(b);
  }
  (views[current] || views['Resumen'])();
}

function resumen(root, m, tname, ctx) {
  for (const t of [0, 1]) {
    const ps = m.players.filter(p => p.team === t);
    const k = ps.reduce((a, p) => a + p.kills, 0), nw = ps.reduce((a, p) => a + p.net_worth, 0);
    root.append(el('h3', {}, el('span', { class: `tag t${t}` }, tname(t)), ` ${m.winning_team === t ? 'Victoria' : 'Derrota'} · ${k} kills · ${fmt.int(nw)} net worth`),
      dataTable([
        { key: 'hero', label: 'Héroe' },
        { key: 'name', label: 'Jugador', render: p => p.player_id ? el('a', { href: '#', onclick: e => { e.preventDefault(); openProfile(p.player_id, ctx); } }, p.name || p.account_id) : String(p.account_id) },
        { key: 'kills', label: 'K' }, { key: 'deaths', label: 'D' }, { key: 'assists', label: 'A' },
        { key: 'net_worth', label: 'Net worth', fmt: 'int' }, { key: 'last_hits', label: 'Last hits' }, { key: 'denies', label: 'Denies' }, { key: 'level', label: 'Nivel' },
        { key: 'comeback_gold_koth', label: 'Comeback Gold Koth', title: '> 0: ganó al menos un KOTH yendo por detrás (no es un recuento)' },
      ], ps, { sortKey: 'net_worth' }), el('div', { style: { height: '12px' } }));
  }
}

function objetivos(root, m, tname) {
  root.append(el('p', { class: 'muted small' }, '«Equipo» es el DUEÑO del objetivo; lo destruye el rival. Si no cayó, se muestra el primer golpe. El mapeo de IDs es inferido (editable en Ajustes).'));
  const cols = [
    { key: 'label', label: 'Objetivo' }, { key: 'objective_id', label: 'ID' },
    { key: 'destroyed_s', label: 'Cae', fmt: 'mmss' },
    { key: 'first_damage_s', label: 'Primer golpe', render: r => r.destroyed_s ? fmt.mmss(r.first_damage_s) : (r.first_damage_s ? `${fmt.mmss(r.first_damage_s)} (no cayó)` : 'sin daño') },
    { key: 'player_damage', label: 'Daño de jugadores', fmt: 'int' }, { key: 'creep_damage', label: 'Daño de tropas', fmt: 'int' },
  ];
  const grid = el('div', { class: 'grid2' });
  for (const t of [0, 1]) {
    const rows = m.objectives.filter(o => o.owner_team === t);
    grid.append(el('div', {}, el('h3', {}, 'Objetivos de ', el('span', { class: `tag t${t}` }, tname(t))), dataTable(cols, rows, { sortKey: 'destroyed_s', asc: true })));
  }
  root.append(el('div', { class: 'row' }, el('button', { onclick: () => csvDownload(`objetivos_${m.match_id}.csv`, [
    { label: 'equipo_dueño', csv: r => r.owner_team }, { label: 'objetivo', csv: r => r.label }, { label: 'id', csv: r => r.objective_id },
    { label: 'cae_s', csv: r => r.destroyed_s ?? '' }, { label: 'cae_mmss', csv: r => r.destroyed_s ? fmt.mmss(r.destroyed_s) : '' },
    { label: 'primer_golpe_s', csv: r => r.first_damage_s ?? '' }], m.objectives) }, 'Exportar CSV')), grid);
  const ev = side => m.objectives.filter(o => o.owner_team === side && o.destroyed_s).map(o => ({ t: o.destroyed_s, label: `${o.label} de ${tname(side)}`, side: side === 0 ? 't0' : 't1', kind: o.type }));
  const mb = m.midboss.map(x => ({ t: x.t, label: `Midboss: lo mata ${tname(x.team_killed)}, lo reclama ${tname(x.team_claimed)}`, side: x.team_killed === 0 ? 't0' : 't1', kind: 'Titan' }));
  root.append(el('h3', { style: { marginTop: '14px' } }, 'Línea de tiempo'),
    el('p', { class: 'muted small' }, 'Color = equipo DUEÑO del objetivo que cae (ámbar = equipo 0, azul = equipo 1).'),
    timeline({ rows: [
      { label: `Pierde ${tname(0)}`, duration: m.duration_s, events: ev(0) },
      { label: `Pierde ${tname(1)}`, duration: m.duration_s, events: ev(1) },
      { label: 'Midboss', duration: m.duration_s, events: mb },
    ] }));
}

function midboss(root, m, tname) {
  root.append(el('div', { class: 'note interpretation' }, el('span', { class: 'lbl' }, 'interpretación'), '«Reclamado» (team_claimed) no está documentado: si lo reclama quien no lo mató, se considera un robo.'),
    el('div', { class: 'unavailable block' }, el('b', {}, 'No disponible: '), 'cristales, quién lo inicia e intentos fallidos (la API no los registra).'),
    m.midboss.length ? dataTable([
      { key: 'n', label: '#' }, { key: 't', label: 'Minuto', fmt: 'mmss' },
      { key: 'team_killed', label: 'Lo mata', render: r => el('span', { class: `tag t${r.team_killed}` }, tname(r.team_killed)) },
      { key: 'team_claimed', label: 'Lo reclama', render: r => el('span', { class: `tag t${r.team_claimed}` }, tname(r.team_claimed)) },
      { key: 'stolen', label: '¿Robo?', render: r => r.stolen ? 'sí (interpretación)' : 'no' },
    ], m.midboss, { sortKey: 't', asc: true }) : el('p', { class: 'muted' }, 'No hubo Midboss.'));
}

async function minimapa(root, m, tname) {
  const status = el('div', {}, spinner('Decodificando posiciones…'));
  root.append(status);
  const [pos, info] = await Promise.all([api.get(`/api/matches/${m.match_id}/positions?step=2`), loadMapInfo()]);
  status.remove();
  const dur = m.duration_s, step = pos.interval_s;
  const st = { team: 'all', slot: 'all', from: 0, to: Math.ceil(dur / 60), heat: true, deaths: true, objectives: false, rotate: false };
  const teamSel = el('select', {}, [['all', 'Ambos equipos'], ['0', tname(0)], ['1', tname(1)]].map(([v, l]) => el('option', { value: v }, l)));
  const slotSel = el('select', {}, el('option', { value: 'all' }, 'Todos los jugadores'),
    m.players.map(p => el('option', { value: p.slot }, `${p.hero} · ${p.name || p.account_id} (${p.team})`)));
  const from = el('input', { type: 'number', min: 0, max: st.to, value: 0, style: { width: '64px' } });
  const to = el('input', { type: 'number', min: 0, max: st.to, value: st.to, style: { width: '64px' } });
  const chk = (key, label) => { const c = el('input', { type: 'checkbox', checked: st[key] }); c.addEventListener('change', () => { st[key] = c.checked; draw(); }); return el('label', {}, c, label); };
  const box = el('div');
  const map = new MapView(box, { size: 820 });
  const counts = el('div', { class: 'muted small' });
  root.append(el('div', { class: 'row' }, teamSel, slotSel, el('label', {}, 'minuto', from, '–', to), chk('heat', 'calor de posiciones'), chk('deaths', 'muertes ✕'),
    chk('objectives', 'objetivos'), chk('rotate', 'girar 180°'), el('button', { onclick: () => map.exportPNG(`minimapa_${m.match_id}.png`) }, 'Exportar PNG')),
    legend([[COLORS.t0, tname(0)], [COLORS.t1, tname(1)], ['#333', 'muerte (color = equipo de la víctima)', 'x']]), counts, box,
    el('p', { class: 'muted small' }, `Calibración: ${info.calibration?.source || '—'}. Las posiciones con vida 0 (muerto) se descartan.`));
  for (const [i, k] of [[teamSel, 'team'], [slotSel, 'slot']]) i.addEventListener('change', () => { st[k] = i.value; draw(); });
  for (const [i, k] of [[from, 'from'], [to, 'to']]) i.addEventListener('input', () => { st[k] = +i.value; draw(); });

  function relToWorld(u, v) {
    const c = info.calibration;
    if (c.invert_x) u = 1 - u; if (c.invert_y !== false) v = 1 - v;
    return [c.x_min + u * (c.x_max - c.x_min), c.y_min + v * (c.y_max - c.y_min)];
  }
  function draw() {
    const t0 = st.from * 60, t1 = st.to * 60;
    const keep = p => (st.team === 'all' || String(p.team) === st.team) && (st.slot === 'all' || String(p.slot) === st.slot);
    const layers = [];
    let n = 0;
    if (st.heat) for (const team of [0, 1]) {
      const pts = [];
      for (const p of pos.players.filter(p => p.team === team && keep(p))) {
        for (let i = Math.floor(t0 / step); i < Math.min(p.x.length, t1 / step); i++) if (p.x[i] != null) pts.push([p.x[i], p.y[i]]);
      }
      n += pts.length;
      layers.push({ kind: 'heat', points: pts, color: team ? COLORS.t1 : COLORS.t0, radius: 12 });
    }
    const deaths = m.deaths.filter(d => d.t >= t0 && d.t <= t1 && keep({ team: d.victim_team, slot: d.victim_slot }) && d.x != null);
    if (st.deaths) layers.push({ kind: 'crosses', points: deaths.map(d => [d.x, d.y, 0, 0, d.victim_team ? COLORS.t1 : COLORS.t0]) });
    if (st.objectives && info.objective_positions) {
      layers.push({ kind: 'markers', points: Object.entries(info.objective_positions).map(([k, v]) => {
        const [x, y] = relToWorld(v.left_relative, v.top_relative);
        return [x, y, k.replace(/^team\d_/, '').replace('tier1_', 'G').replace('tier2_', 'W'), k.startsWith('team0') ? COLORS.t0 : COLORS.t1];
      }) });
    }
    counts.textContent = `${n} posiciones (cada ${step} s) · ${deaths.length} muertes en el rango`;
    map.setLayers(layers, { rotate: st.rotate });
  }
  await map.ready;
  draw();
}

import { api, invalidatePlayers } from '../api.js';
import { el, toast, dataTable, spinner } from '../util.js';
import { resetMapInfo } from '../map.js';

export async function render(root, ctx) {
  const [cfg, roles, om] = await Promise.all([api.get('/api/config'), api.get('/api/roles'), api.get('/api/objective-map')]);

  // ------------------------------------------------------------ configuración
  const f = {
    region: el('select', {}, ['Europe', 'Asia', 'NAmerica', 'SAmerica', 'Oceania'].map(r => el('option', { selected: r === cfg.region }, r))),
    extra_leaderboard_ids: el('input', { value: (cfg.extra_leaderboard_ids || []).join(', ') }),
    update_interval_hours: el('input', { type: 'number', min: 1, value: cfg.update_interval_hours }),
    stats_days: el('input', { type: 'number', min: 1, max: 365, value: cfg.stats_days }),
    stats_match_mode: el('select', {}, [['ranked', 'Ranked only'], ['ranked,unranked', 'Ranked + normal']].map(([v, l]) => el('option', { value: v, selected: (cfg.stats_match_mode || 'ranked') === v }, l))),
    batch_size: el('input', { type: 'number', min: 1, max: 200, value: cfg.batch_size }),
    api_key: el('input', { type: 'password', value: cfg.api_key, placeholder: 'optional (more rate-limit headroom)', autocomplete: 'off' }),
  };
  for (const [k, i] of Object.entries(f)) i.id = 'cfg-' + k;
  f.extra_leaderboard_ids.setAttribute('aria-describedby', 'cfg-extra-help');
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Updates'),
    el('div', { class: 'form-grid', style: { maxWidth: '640px' } },
      el('label', { for: 'cfg-region' }, 'Region'), f.region,
      el('label', { for: 'cfg-extra_leaderboard_ids' }, 'Extra leaderboards'), el('div', {}, f.extra_leaderboard_ids, el('div', { class: 'muted small', id: 'cfg-extra-help' }, 'IDs of past seasons that also contribute players (1001 = Beta Season 1, 1000 players in Europe). The current season is always included.')),
      el('label', { for: 'cfg-update_interval_hours' }, 'Every (hours)'), f.update_interval_hours,
      el('label', { for: 'cfg-stats_days' }, 'Stats from the last (days)'), f.stats_days,
      el('label', { for: 'cfg-stats_match_mode' }, 'Match mode for stats'), f.stats_match_mode,
      el('label', { for: 'cfg-batch_size' }, 'Accounts per request'), f.batch_size,
      el('label', { for: 'cfg-api_key' }, 'API key'), f.api_key),
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { class: 'primary', onclick: async () => {
      try {
        await api.post('/api/config', {
          region: f.region.value, extra_leaderboard_ids: f.extra_leaderboard_ids.value.split(/[\s,;]+/).filter(Boolean).map(Number),
          update_interval_hours: +f.update_interval_hours.value, stats_days: +f.stats_days.value, stats_match_mode: f.stats_match_mode.value, batch_size: +f.batch_size.value, api_key: f.api_key.value,
        });
        toast('Saved. Applies on the next update.');
      } catch (e) { toast(e.message, true); }
    } }, 'Save'))));

  // --------------------------------------------------------------------- roles
  const roleInputs = {};
  const rolesBox = el('div', { class: 'form-grid' });
  const addRole = (name, heroes) => {
    const n = el('input', { value: name, 'aria-label': 'Role name' }), h = el('textarea', { 'aria-label': `Heroes of role ${name}`, style: { minHeight: '40px' } }, heroes.join(', '));
    roleInputs[Math.random()] = [n, h];
    rolesBox.append(n, h);
  };
  for (const [r, hs] of Object.entries(roles.roles)) addRole(r, hs);
  const thr = el('input', { type: 'number', min: 0.05, max: 1, step: 0.05, value: roles.umbral_rol ?? 0.25, style: { width: '80px' } });
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Hero roles'),
    el('p', { class: 'muted small' }, 'A hero can have several roles: its matches are split equally. A player has a role if it makes up at least the threshold share of their matches. Names are compared ignoring case, symbols and "The".'),
    rolesBox,
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { onclick: () => addRole('New role', []) }, 'Add role'),
      el('label', {}, 'Threshold', thr),
      el('button', { class: 'primary', onclick: async () => {
        const out = {};
        for (const [n, h] of Object.values(roleInputs)) if (n.value.trim()) out[n.value.trim()] = h.value.split(',').map(x => x.trim()).filter(Boolean);
        try { await api.post('/api/roles', { roles: out, umbral_rol: +thr.value }); invalidatePlayers(); toast('Roles saved and summaries recomputed'); } catch (e) { toast(e.message, true); }
      } }, 'Save roles'))));

  // ---------------------------------------------------------- objective mapping
  const omRows = Object.entries(om.objetivos).map(([id, o]) => ({ id, ...o }));
  const inputs = {};
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Objective mapping (team_objective_id)'),
    el('p', { class: 'muted small' }, 'Inferred from real timings and consistent with /v1/assets/map (lanes 1, 3 and 4). IDs 2, 6 and 13 do not exist on the current map. Fix it here if a match does not fit.'),
    dataTable([
      { key: 'id', label: 'ID', num: true, sort: r => +r.id },
      { key: 'tipo', label: 'Type', render: r => (inputs[r.id] ??= {}).tipo = el('input', { value: r.tipo, 'aria-label': `Type of objective ${r.id}` }) },
      { key: 'lane', label: 'Lane', sort: r => r.carril ?? '', render: r => inputs[r.id].carril = el('input', { 'aria-label': `Lane of objective ${r.id}`, value: r.carril ?? '', style: { width: '60px' } }) },
      { key: 'n', label: 'No.', render: r => inputs[r.id].n = el('input', { 'aria-label': `Number of objective ${r.id}`, value: r.n ?? '', style: { width: '50px' } }) },
    ], omRows, { sortKey: 'id', asc: true }),
    el('button', { class: 'primary', style: { marginTop: '8px' }, onclick: async () => {
      const objetivos = {};
      for (const [id, i] of Object.entries(inputs)) objetivos[id] = { tipo: i.tipo.value, carril: i.carril.value || null, n: i.n.value || null };
      try { await api.post('/api/objective-map', { objetivos, carriles: om.carriles }); toast('Mapping saved'); } catch (e) { toast(e.message, true); }
    } }, 'Save mapping')));

  // ------------------------------------------------------------- calibration
  const calOut = el('div');
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Minimap calibration'),
    el('p', { class: 'muted small' }, 'Default: the official one from /v1/assets/map (radius 10752, center 0, Y inverted). "Recalibrate" searches for the scale, center and flips that maximize precision × coverage of alive-player positions over the walkable area of the image, using the saved matches.'),
    el('div', { class: 'row' },
      el('button', { onclick: async () => {
        calOut.innerHTML = ''; calOut.append(spinner('Calibrating (can take ~1 min)…'));
        try {
          const r = await api.post('/api/map/calibrate');
          calOut.innerHTML = '';
          calOut.append(el('div', { class: 'muted small' }, `${r.matches} matches · ${r.points} positions`),
            dataTable([{ key: 'name', label: 'Calibration' }, { key: 'precision', label: 'Precision', fmt: 'pct' }, { key: 'coverage', label: 'Coverage', fmt: 'pct' }, { key: 'score', label: 'Precision × coverage', fmt: '2' }],
              Object.entries(r.compare).map(([name, v]) => ({ name, ...v }))),
            el('pre', { class: 'small' }, JSON.stringify(r.fitted, null, 1)),
            el('button', { onclick: async () => { await api.post('/api/map/calibration', { calibration: r.fitted }); resetMapInfo(); toast('Fitted calibration saved'); } }, 'Save the fitted one'));
        } catch (e) { calOut.innerHTML = ''; toast(e.message, true); }
      } }, 'Recalibrate with saved matches'),
      el('button', { onclick: async () => { await api.post('/api/map/calibration', { official: true }); resetMapInfo(); toast('Official calibration restored'); } }, 'Restore the official one')),
    calOut));

  // ------------------------------------------------------------- import
  const path = el('input', { 'aria-label': 'Path to the old scouting.db', placeholder: 'C:\\path\\to\\scouting.db', style: { width: 'min(360px, 100%)' } });
  const impOut = el('pre', { class: 'small' });
  const doImport = dry => async () => {
    try { const r = await api.post('/api/import-old', { path: path.value, dry_run: dry }); impOut.textContent = JSON.stringify(r, null, 1); if (!dry) { invalidatePlayers(); toast('Imported'); } } catch (e) { toast(e.message, true); }
  };
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Import an old scouting.db'),
    el('p', { class: 'muted small' }, 'Imports manual fields (socials, status, notes, team, adult) and snapshot history. It does not overwrite what you already filled in here. Try "Dry run" first.'),
    el('div', { class: 'row' }, path, el('button', { onclick: doImport(true) }, 'Dry run'), el('button', { class: 'primary', onclick: doImport(false) }, 'Import')), impOut));
}

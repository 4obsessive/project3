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
    stats_match_mode: el('select', {}, [['ranked', 'Solo ranked'], ['ranked,unranked', 'Ranked + normales']].map(([v, l]) => el('option', { value: v, selected: (cfg.stats_match_mode || 'ranked') === v }, l))),
    batch_size: el('input', { type: 'number', min: 1, max: 200, value: cfg.batch_size }),
    api_key: el('input', { type: 'password', value: cfg.api_key, placeholder: 'opcional (más margen de rate limit)', autocomplete: 'off' }),
  };
  for (const [k, i] of Object.entries(f)) i.id = 'cfg-' + k;
  f.extra_leaderboard_ids.setAttribute('aria-describedby', 'cfg-extra-help');
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Actualización'),
    el('div', { class: 'form-grid', style: { maxWidth: '640px' } },
      el('label', { for: 'cfg-region' }, 'Región'), f.region,
      el('label', { for: 'cfg-extra_leaderboard_ids' }, 'Leaderboards extra'), el('div', {}, f.extra_leaderboard_ids, el('div', { class: 'muted small', id: 'cfg-extra-help' }, 'IDs de temporadas pasadas que también aportan jugadores (1001 = Beta Season 1, 1000 jugadores en Europa). La temporada actual se incluye siempre.')),
      el('label', { for: 'cfg-update_interval_hours' }, 'Cada (horas)'), f.update_interval_hours,
      el('label', { for: 'cfg-stats_days' }, 'Stats de los últimos (días)'), f.stats_days,
      el('label', { for: 'cfg-stats_match_mode' }, 'Modo de partida de las stats'), f.stats_match_mode,
      el('label', { for: 'cfg-batch_size' }, 'Cuentas por petición'), f.batch_size,
      el('label', { for: 'cfg-api_key' }, 'API key'), f.api_key),
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { class: 'primary', onclick: async () => {
      try {
        await api.post('/api/config', {
          region: f.region.value, extra_leaderboard_ids: f.extra_leaderboard_ids.value.split(/[\s,;]+/).filter(Boolean).map(Number),
          update_interval_hours: +f.update_interval_hours.value, stats_days: +f.stats_days.value, stats_match_mode: f.stats_match_mode.value, batch_size: +f.batch_size.value, api_key: f.api_key.value,
        });
        toast('Guardado. Se aplica en la próxima actualización.');
      } catch (e) { toast(e.message, true); }
    } }, 'Guardar'))));

  // --------------------------------------------------------------------- roles
  const roleInputs = {};
  const rolesBox = el('div', { class: 'form-grid' });
  const addRole = (name, heroes) => {
    const n = el('input', { value: name, 'aria-label': 'Nombre del rol' }), h = el('textarea', { 'aria-label': `Héroes del rol ${name}`, style: { minHeight: '40px' } }, heroes.join(', '));
    roleInputs[Math.random()] = [n, h];
    rolesBox.append(n, h);
  };
  for (const [r, hs] of Object.entries(roles.roles)) addRole(r, hs);
  const thr = el('input', { type: 'number', min: 0.05, max: 1, step: 0.05, value: roles.umbral_rol ?? 0.25, style: { width: '80px' } });
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Roles por héroe'),
    el('p', { class: 'muted small' }, 'Un héroe puede tener varios roles: sus partidas se reparten a partes iguales. Un jugador tiene un rol si pesa al menos el umbral de sus partidas. Los nombres se comparan sin mayúsculas, símbolos ni «The».'),
    rolesBox,
    el('div', { class: 'row', style: { marginTop: '8px' } }, el('button', { onclick: () => addRole('Nuevo rol', []) }, 'Añadir rol'),
      el('label', {}, 'Umbral', thr),
      el('button', { class: 'primary', onclick: async () => {
        const out = {};
        for (const [n, h] of Object.values(roleInputs)) if (n.value.trim()) out[n.value.trim()] = h.value.split(',').map(x => x.trim()).filter(Boolean);
        try { await api.post('/api/roles', { roles: out, umbral_rol: +thr.value }); invalidatePlayers(); toast('Roles guardados y resúmenes recalculados'); } catch (e) { toast(e.message, true); }
      } }, 'Guardar roles'))));

  // ---------------------------------------------------------- mapeo de objetivos
  const omRows = Object.entries(om.objetivos).map(([id, o]) => ({ id, ...o }));
  const inputs = {};
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Mapeo de objetivos (team_objective_id)'),
    el('p', { class: 'muted small' }, 'Inferido de los tiempos reales y coherente con /v1/assets/map (carriles 1, 3 y 4). En el mapa actual no existen 2, 6 ni 13. Corrígelo aquí si una partida no encaja.'),
    dataTable([
      { key: 'id', label: 'ID', num: true, sort: r => +r.id },
      { key: 'tipo', label: 'Tipo', render: r => (inputs[r.id] ??= {}).tipo = el('input', { value: r.tipo, 'aria-label': `Tipo del objetivo ${r.id}` }) },
      { key: 'carril', label: 'Carril', render: r => inputs[r.id].carril = el('input', { 'aria-label': `Carril del objetivo ${r.id}`, value: r.carril ?? '', style: { width: '60px' } }) },
      { key: 'n', label: 'Nº', render: r => inputs[r.id].n = el('input', { 'aria-label': `Número del objetivo ${r.id}`, value: r.n ?? '', style: { width: '50px' } }) },
    ], omRows, { sortKey: 'id', asc: true }),
    el('button', { class: 'primary', style: { marginTop: '8px' }, onclick: async () => {
      const objetivos = {};
      for (const [id, i] of Object.entries(inputs)) objetivos[id] = { tipo: i.tipo.value, carril: i.carril.value || null, n: i.n.value || null };
      try { await api.post('/api/objective-map', { objetivos, carriles: om.carriles }); toast('Mapeo guardado'); } catch (e) { toast(e.message, true); }
    } }, 'Guardar mapeo')));

  // ------------------------------------------------------------- calibración
  const calOut = el('div');
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Calibración del minimapa'),
    el('p', { class: 'muted small' }, 'Por defecto: la oficial de /v1/assets/map (radio 10752, centro 0, Y invertida). «Recalibrar» busca escala, centro e inversiones que maximizan precisión × cobertura de las posiciones de jugadores vivos sobre la zona caminable de la imagen, usando las partidas guardadas.'),
    el('div', { class: 'row' },
      el('button', { onclick: async () => {
        calOut.innerHTML = ''; calOut.append(spinner('Calibrando (puede tardar ~1 min)…'));
        try {
          const r = await api.post('/api/map/calibrate');
          calOut.innerHTML = '';
          calOut.append(el('div', { class: 'muted small' }, `${r.matches} partidas · ${r.points} posiciones`),
            dataTable([{ key: 'name', label: 'Calibración' }, { key: 'precision', label: 'Precisión', fmt: 'pct' }, { key: 'coverage', label: 'Cobertura', fmt: 'pct' }, { key: 'score', label: 'Precisión × cobertura', fmt: '2' }],
              Object.entries(r.compare).map(([name, v]) => ({ name, ...v }))),
            el('pre', { class: 'small' }, JSON.stringify(r.fitted, null, 1)),
            el('button', { onclick: async () => { await api.post('/api/map/calibration', { calibration: r.fitted }); resetMapInfo(); toast('Calibración ajustada guardada'); } }, 'Guardar la ajustada'));
        } catch (e) { calOut.innerHTML = ''; toast(e.message, true); }
      } }, 'Recalibrar con las partidas guardadas'),
      el('button', { onclick: async () => { await api.post('/api/map/calibration', { official: true }); resetMapInfo(); toast('Restaurada la calibración oficial'); } }, 'Restaurar la oficial')),
    calOut));

  // ------------------------------------------------------------- importación
  const path = el('input', { 'aria-label': 'Ruta del scouting.db antiguo', placeholder: 'C:\\ruta\\a\\scouting.db', style: { width: 'min(360px, 100%)' } });
  const impOut = el('pre', { class: 'small' });
  const doImport = dry => async () => {
    try { const r = await api.post('/api/import-old', { path: path.value, dry_run: dry }); impOut.textContent = JSON.stringify(r, null, 1); if (!dry) { invalidatePlayers(); toast('Importado'); } } catch (e) { toast(e.message, true); }
  };
  root.append(el('div', { class: 'panel' }, el('h3', {}, 'Importar un scouting.db antiguo'),
    el('p', { class: 'muted small' }, 'Importa campos manuales (redes, estado, notas, equipo, mayor de edad) e historial de snapshots. No pisa lo que ya hayas rellenado aquí. Prueba primero con «Simular».'),
    el('div', { class: 'row' }, path, el('button', { onclick: doImport(true) }, 'Simular'), el('button', { class: 'primary', onclick: doImport(false) }, 'Importar')), impOut));
}

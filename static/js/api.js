// Acceso a la API local (las escrituras siempre en JSON).
async function handle(r) {
  let data = null;
  try { data = await r.json(); } catch { /* cuerpo vacío */ }
  if (!r.ok) throw new Error((data && data.error) || `HTTP ${r.status}`);
  return data;
}

// Summaries saved by an older build may still carry Spanish enum values; map them to the current ones.
const LEGACY = { Insuficiente: 'Insufficient', Baja: 'Low', Media: 'Medium', Alta: 'High', 'Sin rol': 'No role', 'muestra insuficiente': 'insufficient sample' };
export function normalizePlayer(p) {
  if (!p || typeof p !== 'object') return p;
  if (LEGACY[p.reliability]) p.reliability = LEGACY[p.reliability];
  if (LEGACY[p.role_text]) p.role_text = LEGACY[p.role_text];
  for (const r of p.role_breakdown || []) if (LEGACY[r[0]]) r[0] = LEGACY[r[0]];
  for (const h of p.heroes || []) if (LEGACY[h.reliability]) h.reliability = LEGACY[h.reliability];
  return p;
}

export const api = {
  get: url => fetch(url).then(handle),
  post: (url, body = {}) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: typeof body === 'string' ? body : JSON.stringify(body) }).then(handle),
};

// cachés compartidas entre vistas
let playersCache = null, heroesCache = null;
export async function getPlayers(force = false) {
  if (!playersCache || force) playersCache = (await api.get('/api/players')).map(normalizePlayer);
  return playersCache;
}
export function invalidatePlayers() { playersCache = null; }
export async function getHeroes() {
  if (!heroesCache) heroesCache = await api.get('/api/heroes');
  return heroesCache;
}
export function heroName(heroes, id) {
  const h = heroes.find(h => h.id === id);
  return h ? h.name : `#${id}`;
}

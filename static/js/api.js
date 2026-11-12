// Acceso a la API local (las escrituras siempre en JSON).
async function handle(r) {
  let data = null;
  try { data = await r.json(); } catch { /* cuerpo vacío */ }
  if (!r.ok) throw new Error((data && data.error) || `HTTP ${r.status}`);
  return data;
}

export const api = {
  get: url => fetch(url).then(handle),
  post: (url, body = {}) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: typeof body === 'string' ? body : JSON.stringify(body) }).then(handle),
};

// cachés compartidas entre vistas
let playersCache = null, heroesCache = null;
export async function getPlayers(force = false) {
  if (!playersCache || force) playersCache = await api.get('/api/players');
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

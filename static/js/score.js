// Score 0–100 con pesos ajustables. KDA y winrate se suavizan hacia la media con
// PRIOR partidas "ficticias", para que una muestra pequeña no gane.
export const DEFAULT_WEIGHTS = { kda: 35, winrate: 30, volume: 20, flex: 15 };
const PRIOR = 10;

export function computeScores(players, weights) {
  const act = players.filter(p => p.stats.matches > 0);
  let K = 0, D = 0, A = 0, W = 0, M = 0;
  for (const p of act) { K += p.stats.kills; D += p.stats.deaths; A += p.stats.assists; W += p.stats.wins; M += p.stats.matches; }
  const meanKDA = (K + A) / Math.max(D, 1), meanWR = M ? W / M : 0.5, dPerGame = M ? D / M : 6;
  const maxM = Math.max(1, ...act.map(p => p.stats.matches));
  for (const p of players) {
    const s = p.stats;
    if (!s.matches) { p._kdaS = p._wrS = p.score = null; continue; }
    p._kdaS = (s.kills + s.assists + PRIOR * dPerGame * meanKDA) / (s.deaths + PRIOR * dPerGame);
    p._wrS = (s.wins + PRIOR * meanWR) / (s.matches + PRIOR);
    p._vol = Math.log1p(s.matches) / Math.log1p(maxM);
    p._flex = 1 - (p.top_hero_share ?? 1);
  }
  const pr = key => {
    const v = act.map(p => p[key]).sort((a, b) => a - b);
    return x => { let lo = 0, hi = v.length; while (lo < hi) { const m = (lo + hi) >> 1; if (v[m] < x) lo = m + 1; else hi = m; } return v.length > 1 ? lo / (v.length - 1) : 1; };
  };
  const rk = pr('_kdaS'), rw = pr('_wrS');
  const tot = (weights.kda + weights.winrate + weights.volume + weights.flex) || 1;
  for (const p of act) {
    p.score = 100 * (weights.kda * rk(p._kdaS) + weights.winrate * rw(p._wrS) + weights.volume * p._vol + weights.flex * p._flex) / tot;
  }
  return { meanKDA, meanWR };
}

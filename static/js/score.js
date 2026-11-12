// Score v2: el servidor calcula los componentes (percentiles 0–1 frente a jugadores con ≥20 partidas,
// ya ajustados por héroe y encogidos según la muestra). Aquí solo se aplican los pesos.
import { store } from './util.js';

export const DEFAULT_WEIGHTS = { win: 30, kda: 25, dmg: 15, econ: 15, obj: 5, pool: 10 };
export const WEIGHT_LABELS = [
  ['win', 'Winrate ajustado'], ['kda', 'KDA (índice por héroe)'], ['dmg', 'Daño/min (índice)'],
  ['econ', 'Oro/min (índice)'], ['obj', 'Objetivos/min (índice)'], ['pool', 'Variedad de héroes'],
];

/** Pesos guardados (migra la clave antigua `weights` a `weights2`: el modelo cambió, se empieza de cero). */
export function loadWeights() {
  const w = store.get('weights2', null);
  if (w && typeof w === 'object') return { ...DEFAULT_WEIGHTS, ...w };
  try { localStorage.removeItem('dls.weights'); } catch { /* sin almacenamiento */ }
  return { ...DEFAULT_WEIGHTS };
}
export function saveWeights(w) { store.set('weights2', w); }

function combine(parts, w) {
  let tot = 0, s = 0;
  for (const k of Object.keys(DEFAULT_WEIGHTS)) {
    const wk = Math.max(0, +w[k] || 0);
    tot += wk;
    s += wk * (parts[k] ?? 0.5);
  }
  return tot ? 100 * s / tot : null;
}

/** Añade p.score, p.score_lo, p.score_hi con los pesos dados. */
export function computeScores(players, weights) {
  for (const p of players) {
    const parts = p.score_parts;
    if (!parts) { p.score = p._lo = p._hi = null; continue; }
    p.score = combine(parts, weights);
    const band = p.score_win_band;
    p._lo = band ? combine({ ...parts, win: band[0] }, weights) : null;
    p._hi = band ? combine({ ...parts, win: band[1] }, weights) : null;
  }
}

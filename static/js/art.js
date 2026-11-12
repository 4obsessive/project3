// Arte del juego: retratos de héroes, imágenes de objetivos y pastillas de carril.
// Todo se pide al proxy local (/img/...); nunca al exterior (CSP: img-src 'self').
import { el } from './util.js';
import { icon } from './icons.js';
import { api } from './api.js';

/** "Mo & Krill" -> "Mo_%26_Krill_vertical.png" */
export function wikiHeroFile(name) {
  return String(name).trim().replace(/&/g, '%26').replace(/\s+/g, '_') + '_vertical.png';
}

function initial(name, size, shape) {
  const ch = (String(name || '?').trim()[0] || '?').toUpperCase();
  return el('span', { class: `avatar initial ${size} ${shape}`, 'aria-label': name || '' }, ch);
}

/** Retrato: wiki -> imagen de la API -> inicial. */
export function heroPortrait(hero, { size = 'md', shape = 'card' } = {}) {
  const name = hero.name || '';
  const chain = [hero.wiki_image || '/img/wiki/' + wikiHeroFile(name), hero.image].filter(Boolean);
  const img = el('img', { class: `portrait ${size} ${shape}`, loading: 'lazy', alt: name, src: chain[0] });
  let i = 0;
  img.addEventListener('error', () => {
    i += 1;
    if (i < chain.length) img.src = chain[i];
    else img.replaceWith(initial(name, size, shape));
  });
  return img;
}

const WIKI_OBJ = {
  walker: 'Walker_Icon.png',
  shrine: 'Shrines.png',
  titan: 'Patrons.png',
  core: 'Patrons.png',
  midboss: 'Mid-Boss_model.png',
  rejuvenator: 'Rejuvenator_crystal.png',
  koth: 'Unstable_Rift.png',
};
const OBJ_ICON = { walker: 'sword', shrine: 'star', titan: 'trophy', core: 'trophy',
  midboss: 'star', rejuvenator: 'star', koth: 'star' };

function objKey(type) {
  const t = String(type || '').toLowerCase().replace(/[\s_-]+/g, '');
  if (t.includes('baseguardian')) return 'baseguardian';
  if (t.includes('guardian')) return 'guardian';
  if (t.includes('walker')) return 'walker';
  if (t.includes('shrine')) return 'shrine';
  if (t.includes('titan') || t.includes('patron')) return 'titan';
  if (t.includes('core')) return 'core';
  if (t.includes('midboss')) return 'midboss';
  if (t.includes('rejuvenator')) return 'rejuvenator';
  if (t.includes('koth') || t.includes('rift')) return 'koth';
  return t;
}

function guardianSvg(size) {
  return el('span', { class: `obj-img ${size} obj-guardian`, role: 'img', 'aria-label': 'Guardián',
    html: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 22 12 12 22 2 12z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>' });
}

/** Imagen de un objetivo según su tipo (y equipo dueño para las bases). */
export function objectiveImg(type, ownerTeam = null, { size = 'md' } = {}) {
  const k = objKey(type);
  if (k === 'guardian') return guardianSvg(size);
  let file = WIKI_OBJ[k];
  if (k === 'baseguardian') file = ownerTeam === 1 ? 'Archmother_base_guardians.png' : 'Hidden_King_base_guardians.png';
  const fallback = () => el('span', { class: `obj-img ${size} obj-fallback`, role: 'img', 'aria-label': String(type) },
    icon(OBJ_ICON[k] || 'grid'));
  if (!file) return fallback();
  const img = el('img', { class: `obj-img ${size}`, loading: 'lazy', alt: String(type), src: '/img/wiki/' + file });
  img.addEventListener('error', () => img.replaceWith(fallback()));
  return img;
}

const LANE_FALLBACK = {
  1: { nombre: 'York', color: '#F1CC30', alias: 'amarillo' },
  3: { nombre: 'Broadway', color: '#29b1cc', alias: 'azul' },
  4: { nombre: 'Greenwich', color: '#59b247', alias: 'verde' },
};

export function laneStyle(laneId, lanes) {
  const l = (lanes && lanes[laneId]) || LANE_FALLBACK[laneId];
  return l ? { nombre: l.nombre, color: l.color || 'var(--muted)', alias: l.alias }
    : { nombre: `Carril ${laneId}`, color: 'var(--muted)', alias: '' };
}

export function laneChip(laneId, lanes) {
  const l = laneStyle(laneId, lanes);
  return el('span', { class: 'lane-chip', style: { '--lane': l.color } },
    el('span', { class: 'lane-dot', 'aria-hidden': 'true' }),
    l.nombre, l.alias ? el('small', {}, ' · ' + l.alias) : null);
}

let lanesCache = null;
/** { "1": {nombre,color,alias}, ... } desde /api/objective-map (cacheado). */
export async function getLanes() {
  if (!lanesCache) {
    const om = await api.get('/api/objective-map');
    const out = {};
    for (const [id, nombre] of Object.entries(om.carriles || {})) {
      const c = (om.colores || {})[id] || {};
      out[id] = { nombre, color: c.color, alias: c.alias };
    }
    lanesCache = out;
  }
  return lanesCache;
}

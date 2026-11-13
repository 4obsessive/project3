# Design: kills/deaths without objective fights, more visual stats, English UI

Date: 2026-11-13 · Status: draft, pending user approval

## Intent

The app is used to prepare matches against a rival and to analyse one's own team. The user wants:
1. Next to the kills and deaths on the map, the same statistics **excluding midboss fights and KOTH fights**, to see how
   the team fights in the rest of the match.
2. Statistics **more visual**, using more images, **without removing anything important**.
3. **Everything in English** (the user interface).

Binding rules still in force: everything in the team report comes from each match, and the match view shows the same
numbers for one match; nothing invented or interpreted (missing data → "not available"/"–"; findings only as counts);
lanes by name and colour, never by side.

## Objective-fight definition (decided with the user, 2026-11-13)

Every kill/death event (metadata `death_details`, exact second and position) is classified as **midboss fight**,
**KOTH fight** or **rest**:

- **Midboss fight**: the death happens **near the midboss pit** (map centre, world (0,0)) and inside the window
  **from the first damage to the midboss until 60 s after it dies**. With demo data, the first damage and the death come
  from the stored midboss damage rows (`t0`/`t1` ticks per midboss entity, converted with the existing tick→seconds
  function). **Without demo**: window = 60 s before the midboss death (metadata `mid_boss[].destroyed_time_s`) until 60 s
  after.
- **KOTH fight**: the death happens **near one of the two rifts** (world (−7648, 0) and (7648, 0), from
  `/v1/assets/map` `entities.unstable_rifts`) and inside the window **from cash-in start until 60 s after it completes or
  is abandoned** (demo summary `koth[]`: `start_t`, `completed_t`; abandoned → the give-up time if stored, otherwise
  start + the cash-in duration the data shows; the builder checks what the stored raw rules allow). **Without demo**: no
  KOTH timing exists → KOTH fights cannot be identified; such matches say so ("KOTH fights not identifiable without the
  match demo") and are excluded from "without objective fights" figures rather than guessing.
- A death that matches both counts once, as midboss fight if nearer the pit, else KOTH.
- "Near": builder's call, one radius per objective, documented (proposal: 2500 world units around the pit, 2000 around
  each rift); kills elsewhere on the map during the window are "rest".

## Goals

1. **Kills/deaths excluding objective fights**, everywhere kills/deaths are shown on the map today:
   - Report, map section (m02): next to the existing kills/deaths maps and zone tables, the same maps/tables computed
     over "rest" events only, plus a small summary: total kills/deaths, how many were midboss fights, how many KOTH
     fights, and the rest (with n matches and how many matches lacked demo for KOTH).
   - Report, players section (m08) and the match view «Jugadores» tab: per player, kills/deaths and their zone maps
     with and without objective fights.
   - Match view: the same split for that match (map layers toggle or side-by-side).
2. **More visual, nothing removed**: keep every table and number; add hero portraits wherever a hero or player appears,
   objective icons (Guardian, Walker, Midboss, Rejuvenator, Rift) in titles and columns, lane chips, in-cell mini bars
   for comparable numbers, and highlight cards with images for headline facts (e.g. the duo dealing most damage per
   lane, the player with most kills). Reuse the wiki/API image proxy already in the app (no new hosts, no committed
   Valve art).
3. **English UI**: translate every user-facing string in place (views, report metric texts/titles/columns/notes,
   findings, tooltips, errors shown to the user, page titles, number/date formatting to an English locale). Game names
   (heroes, lanes York/Broadway/Greenwich, team names Hidden King/Archmother) stay as they are. Spanish disappears from
   the UI. Server log messages and code comments may stay in Spanish. README/HANDOFF stay in Spanish (they are for the
   developer) — builder's call to add a short English note.

## Non-goals

- A language switch (approach B was rejected).
- New statistics beyond the objective-fight split.
- Soul urn (still deferred).

## Anti-goals

- Removing or hiding any existing statistic to make room for images.
- Guessing KOTH fights without demo data.
- Report and match view disagreeing on the split for the same match.

## Approaches

- Objective-fight split: one shared per-match classifier used by report and match view (only sensible way).
- English: **A, translate in place** (chosen by the user) vs B, i18n with a language switch (rejected: double work,
  risk of untranslated strings).
- Visual: augment existing blocks with images and small visual elements (chosen as my call) vs a new dashboard layout
  (rejected: would move/remove existing content).

## Constraints

- Python 3.15 stdlib, vanilla JS, existing CSP (images only via the app's proxy).
- Tests must keep passing; tests that assert Spanish strings are updated to English.
- Do the English and visual work screen by screen in one pass (they touch the same files).

## Decisions from the review (my calls; the user can correct them)

- **No-demo matches:** midboss fights are identified from metadata; KOTH fights are not. Such a match is marked
  "KOTH unknown" and is **excluded** from the "without objective fights" maps/tables/player split (the report says how
  many matches were excluded). Its normal kills/deaths still count where they count today.
- **Which rift:** the stored demo data has no cash-in location, so during a cash-in window a death near **either** rift
  counts as a KOTH fight. The two rifts are ~15 000 units apart, so this rarely matters; documented.
- **Abandoned cash-ins:** the stored raw demo rows include `koth_give_up`; extend the demo summary with each cash-in's
  end time (completed, or the give-up/abandon time from the raw rows) and bump `SUMMARY_VERSION` — summaries are rebuilt
  from the stored raw rows automatically, with no new API queries.
- **One window per midboss kill** (each midboss of the match has its own window).
- **Position used:** the victim's death position, for both kills and deaths (same convention as the existing maps).
- **Images:** the app's proxy already serves objective images (Guardian, Walker, Midboss, Rejuvenator, Unstable Rift)
  via `art.js`; no new hosts.
- **Tests:** updating tests to English strings is in scope; add a test that scans `static/js` and report metric texts
  for leftover common Spanish words.

## Left to the builder

- Exact radii (documented), the data structure of the classifier output, how the split is presented (side-by-side vs
  toggle) within the current style, which headline cards to add, English wording.

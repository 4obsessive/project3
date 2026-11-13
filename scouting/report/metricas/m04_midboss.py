"""Midboss: cuándo, quién lo mata y quién lo reclama, kills en la ventana y diferencia de net worth."""
from collections import Counter

from .. import metric, stats
from ... import matches as M

REGLA = "net worth (interpolated from the match samples) < 0.9 × the enemy's (10% rule)"


@metric("midboss", "Midboss", order=40)
def midboss(ctx):
    win = int(ctx.params.get("midboss_window_s") or 90)
    events = []
    matches_with = 0
    first_by = Counter()
    for m in ctx.matches:
        mb = M.midboss(m.mi)
        if mb:
            matches_with += 1
            first_by[m.rel(mb[0]["team_killed"])] += 1
        for e in mb:
            t = e["t"]
            if t is None:  # sin segundo: nada que contar en la ventana (dato ausente, no 0)
                k_us = k_them = kill_adv = nw_adv = None
            else:
                dt = [d for d in m.deaths if d["t"] is not None]
                k_us = sum(1 for d in dt if d["killer_team"] == m.our and d["victim_team"] == m.their and t - win <= d["t"] <= t)
                k_them = sum(1 for d in dt if d["killer_team"] == m.their and d["victim_team"] == m.our and t - win <= d["t"] <= t)
                cum_us = sum(1 for d in dt if d["killer_team"] == m.our and d["victim_team"] == m.their and d["t"] <= t)
                cum_them = sum(1 for d in dt if d["killer_team"] == m.their and d["victim_team"] == m.our and d["t"] <= t)
                kill_adv = cum_us - cum_them
                nw_adv = round(M.team_networth_at(m.mi, m.our, t) - M.team_networth_at(m.mi, m.their, t))
            events.append({
                "match_id": m.id, "n": e["n"], "t": t, "killer": m.rel(e["team_killed"]), "claimer": m.rel(e["team_claimed"]),
                "kills_us": k_us, "kills_them": k_them, "kill_adv": kill_adv,
                "nw_adv": nw_adv, "won": m.won,
            })
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info",
               "text": f"Window for prior kills: {win} s. The net worth difference is the one at that second (interpolated from samples every few minutes)."}]
    if not events:
        blocks.append({"type": "text", "tone": "confirmed", "text": f"No Midboss in any of the {n} matches."})
        return blocks
    ours = [e for e in events if e["killer"] == "us"]
    theirs = [e for e in events if e["killer"] == "them"]
    blocks.append({"type": "text", "tone": "confirmed",
                   "text": f"Midboss in {matches_with} of {n} matches ({len(events)} Midboss kills). This team kills it {len(ours)} times and the enemy {len(theirs)}. "
                           f"First of the match: this team {first_by['us']}, enemy {first_by['them']}."})
    rows = []
    for label, evs in (("This team", ours), ("Enemy", theirs), ("First Midboss of this team", [e for e in ours if e["n"] == 1]),
                       ("First Midboss of the enemy", [e for e in theirs if e["n"] == 1])):
        s = stats([e["t"] for e in evs])
        rows.append({"quien": label, "veces": len(evs), "media": s["mean"], "mediana": s["median"], "min": s["min"], "max": s["max"]})
    blocks.append({"type": "table", "title": "Midboss minute", "n": n,
                   "columns": [{"key": "quien", "label": "Killed by", "objective": "Midboss"}, {"key": "veces", "label": "Times", "bar": True}, {"key": "media", "label": "Mean", "fmt": "mmss"},
                               {"key": "mediana", "label": "Median", "fmt": "mmss"}, {"key": "min", "label": "Min", "fmt": "mmss"}, {"key": "max", "label": "Max", "fmt": "mmss"}],
                   "rows": rows})
    blocks.append({"type": "histogram", "title": "Midboss minute", "bin_s": 120, "n": n,
                   "series": [{"name": "This team", "side": "us", "values": [e["t"] for e in ours if e["t"] is not None]},
                              {"name": "Enemy", "side": "them", "values": [e["t"] for e in theirs if e["t"] is not None]}]})
    scen = []
    for label, evs in (("When this team kills it", ours), ("When the enemy kills it", theirs)):
        if not evs:
            scen.append({"escenario": label, "veces": 0})
            continue
        scen.append({
            "escenario": label, "veces": len(evs),
            "kills_us": stats([e["kills_us"] for e in evs])["mean"], "kills_them": stats([e["kills_them"] for e in evs])["mean"],
            "kill_adv": stats([e["kill_adv"] for e in evs])["median"], "nw_adv": stats([e["nw_adv"] for e in evs])["median"],
            "ganadas": sum(1 for e in evs if e["won"]),
        })
    blocks.append({"type": "table", "title": "Scenarios (from this team's point of view)", "n": n,
                   "columns": [{"key": "escenario", "label": "Scenario", "objective": "Midboss"}, {"key": "veces", "label": "Times"},
                               {"key": "kills_us", "label": f"Own kills in {win}s (mean)", "fmt": "1"},
                               {"key": "kills_them", "label": f"Enemy kills in {win}s (mean)", "fmt": "1"},
                               {"key": "kill_adv", "label": "Kill lead (median)", "fmt": "signed"},
                               {"key": "nw_adv", "label": "Net worth lead (median)", "fmt": "signed0"},
                               {"key": "ganadas", "label": "Matches won"}],
                   "rows": scen})
    blocks.append({"type": "table", "title": "Detail", "n": n,
                   "columns": [{"key": "match_id", "label": "Match"}, {"key": "n", "label": "#"}, {"key": "t", "label": "Time", "fmt": "mmss"},
                               {"key": "killer_txt", "label": "Killed by", "objective": "Midboss"}, {"key": "claimer_txt", "label": "Claimed by"},
                               {"key": "kills_us", "label": "Own kills"}, {"key": "kills_them", "label": "Enemy kills"},
                               {"key": "kill_adv", "label": "Kill lead", "fmt": "signed"}, {"key": "nw_adv", "label": "NW lead", "fmt": "signed0"}],
                   "rows": [dict(e, killer_txt="This team" if e["killer"] == "us" else "Enemy",
                                 claimer_txt="This team" if e["claimer"] == "us" else "Enemy") for e in events]})
    blocks.extend(_demo_blocks(ctx))
    # patrones
    if n >= 3:
        if first_by["us"] / n >= 0.6:
            ctx.finding("strength", f"They take the first Midboss in {first_by['us']} of {n} matches.", first_by["us"], n)
    return blocks


def _yn(v):
    return "—" if v is None else ("yes" if v else "no")


def _remontada(mi, t, team):
    """«yes»/«no» si el equipo `team` estaba en remontada en t; «—» si falta el equipo, el segundo o el net worth."""
    if team is None:
        return "—"
    cb = M.comeback_team_at(mi, t)
    return "—" if cb is None else _yn(cb == team)


def _demo_blocks(ctx):
    k = ctx.demo_n
    cov = ctx.demo_coverage()
    if not k:
        return [cov, {"type": "unavailable", "title": "Midboss damage, rejuvenators and steals (demo)",
                      "reason": "No analysed match has demo data (pending, no demo, or failed)."}]
    rows = []
    taken_us = taken_them = steals_made = steals_suffered = 0
    for m in ctx.matches:
        d = m.demo
        if not d:
            continue
        for e in d.get("midboss") or []:
            dm, rj = e.get("damage") or {}, e.get("rejuv") or {}
            taken_us += rj.get(str(m.our), 0)
            taken_them += rj.get(str(m.their), 0)
            if e.get("stolen"):
                if e.get("killer") == m.our:
                    steals_made += 1
                elif e.get("killer") == m.their:
                    steals_suffered += 1
            kt = e.get("killer")
            rows.append({
                "match_id": m.id, "n": e.get("n"), "t": e.get("t"),
                "dano_nuestro": dm.get(str(m.our)), "dano_rival": dm.get(str(m.their)),
                "iniciador": {"us": "This team", "them": "Enemy"}.get(m.rel(e.get("initiator")), "—"),
                "robado": _yn(e.get("stolen")),
                "rejuv_nuestros": rj.get(str(m.our)), "rejuv_rival": rj.get(str(m.their)),
                "remontada": _remontada(m.mi, e.get("t"), kt),
            })
    out = [cov]
    if not rows:
        out.append({"type": "unavailable", "title": "Midboss damage, rejuvenators and steals (demo)",
                    "reason": "The analysed demos record no Midboss kill."})
        return out
    out.append({"type": "text", "tone": "info",
                "text": "Initiator: the team that dealt the most damage to the Midboss. Stolen: killed by the team that did not start it (only when damage is recorded). "
                        f"Comeback: the team that kills it had {REGLA} at that second; «—» if there are no net worth samples."})
    n_mb = len(rows)
    out.append({"type": "text", "tone": "confirmed",
                "text": f"Rejuvenators taken in {n_mb} Midboss: this team {taken_us} (mean {taken_us / n_mb:.1f} per Midboss), enemy {taken_them} (mean {taken_them / n_mb:.1f}). "
                        f"Steals: by this team {steals_made}, suffered {steals_suffered}. "
                        f"Midboss killed during a comeback of the killer: {sum(1 for r in rows if r['remontada'] == 'yes')} of {n_mb}."})
    out.append({"type": "table", "title": "Midboss: damage, rejuvenators and steal (demo)", "n": k,
                "columns": [{"key": "match_id", "label": "Match"}, {"key": "n", "label": "#"}, {"key": "t", "label": "Time", "fmt": "mmss"},
                            {"key": "dano_nuestro", "label": "Damage this team", "fmt": "int", "bar": True}, {"key": "dano_rival", "label": "Damage enemy", "fmt": "int", "bar": True},
                            {"key": "iniciador", "label": "Started by"}, {"key": "robado", "label": "Stolen"},
                            {"key": "rejuv_nuestros", "label": "Rejuv. this team", "objective": "Rejuvenator"}, {"key": "rejuv_rival", "label": "Rejuv. enemy", "objective": "Rejuvenator"},
                            {"key": "remontada", "label": "In comeback"}],
                "rows": rows})
    return out

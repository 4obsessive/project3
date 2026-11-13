"""Resumen de la fase de líneas (0-600 s) de una partida: dúos por línea, daño, Guardians y gankeos."""
from . import demo, lanes as lanes_mod, matches

T_FIN = 600
T_GANK = 60


def _slot_of(mi):
    return {p["account_id"]: p["player_slot"] for p in mi.get("players") or []}


def _interp_dmg(mi, t=T_FIN):
    """({slot: hecho}, {slot: recibido}) contra héroes enemigos, interpolando el acumulado de damage_matrix a `t`."""
    dm = mi.get("damage_matrix") or {}
    samples = dm.get("sample_time_s") or []
    team = {p["player_slot"]: p.get("team") for p in mi.get("players") or []}
    done = {s: 0.0 for s in team}
    taken = {s: 0.0 for s in team}
    if not samples:
        return {s: 0 for s in team}, {s: 0 for s in team}
    ts = [0] + list(samples)

    def at(arr):
        vals = [0] + list(arr)
        vals += [vals[-1]] * (len(ts) - len(vals))   # los acumulados cortos se mantienen
        if t >= ts[-1]:
            return vals[-1]
        for i in range(1, len(ts)):
            if t <= ts[i]:
                return vals[i - 1] + (vals[i] - vals[i - 1]) * (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return vals[-1]

    for dealer in dm.get("damage_dealers") or []:
        a = dealer.get("dealer_player_slot")
        if a not in team:
            continue
        for src in dealer.get("damage_sources") or []:
            for tg in src.get("damage_to_players") or []:
                v = tg.get("target_player_slot")
                if v not in team or team[v] == team[a]:
                    continue
                x = at(tg.get("damage") or [])
                done[a] += x
                taken[v] += x
    return {s: int(round(v)) for s, v in done.items()}, {s: int(round(v)) for s, v in taken.items()}


def _event(t, att, vic, kind):
    return {"t": int(round(t)), "attacker_slot": att, "victim_slot": vic, "kind": kind}


def _better(cur, new):
    """El evento más temprano; a igual t gana la kill."""
    if cur is None:
        return new
    if (new["t"], new["kind"] != "kill") < (cur["t"], cur["kind"] != "kill"):
        return new
    return cur


def lane_phase(mi, lane_rows=None, rules=None, paths=None):
    ps = matches.players(mi)
    team = {s: p.get("team") for s, p in ps.items()}
    lane_of = lanes_mod.assign_lanes(mi, paths if paths is not None else lanes_mod.load_paths())
    duo = lanes_mod.duos(mi, lane_of)
    valid = bool(duo)
    use_demo = lane_rows is not None and rules is not None

    d_done = {s: 0 for s in ps}
    d_taken = {s: 0 for s in ps}
    d_done_l = {s: 0 for s in ps}
    d_taken_l = {s: 0 for s in ps}
    d_taken_g = {s: 0 for s in ps}
    gank_ev = []   # (t, att, vic, kind) cruzados
    if use_demo:
        by_acc = _slot_of(mi)
        for r in lane_rows:
            a, v = by_acc.get(r["att"]), by_acc.get(r["vic"])
            if a is None or v is None or team[a] == team[v] or not r.get("dmg"):
                continue
            t = demo.game_seconds_from_tick(r["b"] * 320, rules)
            if t < 0 or t > T_FIN:
                continue
            d_done[a] += r["dmg"]
            d_taken[v] += r["dmg"]
            if valid:
                if lane_of[a] == lane_of[v]:
                    d_done_l[a] += r["dmg"]
                    d_taken_l[v] += r["dmg"]
                else:
                    d_taken_g[v] += r["dmg"]
                    if t >= T_GANK and r["dmg"] > 0:
                        gank_ev.append(_event(t, a, v, "dano"))
    else:
        d_done, d_taken = _interp_dmg(mi)
        for s in ps:
            d_done.setdefault(s, 0)
            d_taken.setdefault(s, 0)

    deaths, kills = {s: 0 for s in ps}, {s: 0 for s in ps}
    for d in matches.deaths(mi):
        t = d["t"]
        if t is None or t >= T_FIN:
            continue
        deaths[d["victim_slot"]] += 1
        k = d["killer_slot"]
        if k is not None and d["killer_team"] != d["victim_team"]:
            kills[k] += 1
            if valid and t >= T_GANK and lane_of[k] != lane_of[d["victim_slot"]]:
                gank_ev.append(_event(t, k, d["victim_slot"], "kill"))

    # Guardians
    guard = {}
    for o in matches.objectives(mi):
        if o["type"] == "Guardian" and o["destroyed_s"]:
            guard[(o["lane"], o["owner_team"])] = o["destroyed_s"]

    made, suffered = {}, {}
    ganks_made = {s: 0 for s in ps}
    ganks_suffered = {s: 0 for s in ps}
    for e in gank_ev:
        a, v = e["attacker_slot"], e["victim_slot"]
        k = (lane_of[v], team[a])          # gankea el equipo de a en la línea de v
        made[k] = _better(made.get(k), e)
        k = (lane_of[v], team[v])
        suffered[k] = _better(suffered.get(k), e)
    for e in gank_ev:
        ganks_made[e["attacker_slot"]] += 1
        ganks_suffered[e["victim_slot"]] += 1

    def tot(d, slots, on):
        return sum(d[s] for s in slots) if on else None

    out_lanes = {}
    for tm, per_lane in duo.items():
        for ln, slots in per_lane.items():
            enemy = 1 - tm
            out_lanes.setdefault(str(ln), {})[str(tm)] = {
                "slots": slots,
                "heroes": [ps[s].get("hero_id") for s in slots],
                "dmg_done": tot(d_done, slots, True), "dmg_taken": tot(d_taken, slots, True),
                "dmg_done_lane": tot(d_done_l, slots, use_demo),
                "dmg_taken_lane": tot(d_taken_l, slots, use_demo),
                "dmg_taken_gank": tot(d_taken_g, slots, use_demo),
                "guardian_taken_t": guard.get((ln, enemy)), "guardian_lost_t": guard.get((ln, tm)),
                "deaths": sum(deaths[s] for s in slots), "kills": sum(kills[s] for s in slots),
                "first_gank_suffered": suffered.get((ln, tm)),
                "first_gank_made": made.get((ln, tm)),
            }
    players = {str(s): {"lane": lane_of.get(s) if valid else None,
                        "dmg_done": d_done[s], "dmg_taken": d_taken[s],
                        "ganks_made": ganks_made[s], "ganks_suffered": ganks_suffered[s],
                        "deaths": deaths[s], "kills": kills[s]} for s in sorted(ps)}
    return {"valid": valid, "source": "demo" if use_demo else "aprox", "lanes": out_lanes, "players": players}

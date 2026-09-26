"""The PHC Pulse engine: loads the warehouse into arrays, runs forecasting, early warning,
anomaly detection and redistribution, and caches the result until new data arrives."""
import json
import threading
import time
from datetime import date, timedelta

import numpy as np

from . import anomaly, config, forecasting, redistribution
from .db import get_conn, rows
from .geo import distance_matrix_km
from .reference import DRUG_BY_CODE, DRUGS, LIFE_SAVING

DRUG_CODES = [d["code"] for d in DRUGS]
SYNDROME_DRUGS = {"fever": ["PCM", "ACT"], "diarrhoea": ["ORS", "ZNC"], "respiratory": ["AMX"]}

_state = {"version": 0, "result": None, "computed_version": -1, "cross_state": None}
_lock = threading.RLock()


def invalidate():
    with _lock:
        _state["version"] += 1


def get(allow_cross_state: bool = False) -> dict:
    with _lock:
        if (_state["result"] is None or _state["computed_version"] != _state["version"]
                or _state["cross_state"] != allow_cross_state):
            _state["result"] = compute(allow_cross_state)
            _state["computed_version"] = _state["version"]
            _state["cross_state"] = allow_cross_state
        return _state["result"]


def _next_supply_days(anchor: date, day: date) -> int:
    """Days from `day` until the next scheduled monthly delivery (>= 1)."""
    cyc = config.SUPPLY_CYCLE_DAYS
    return ((anchor - day).days - 1) % cyc + 1


def load():
    with get_conn() as conn:
        phcs = rows(conn, "SELECT * FROM phcs ORDER BY id")
        districts = rows(conn, "SELECT * FROM districts")
        states = rows(conn, "SELECT * FROM states")
        stock = rows(conn, "SELECT phc_id, drug_code, day, dispensed, unmet, closing, source "
                           "FROM stock_daily")
        foot = rows(conn, "SELECT * FROM footfall_daily")
        transfers = rows(conn, "SELECT * FROM transfers")
    return phcs, districts, states, stock, foot, transfers


def compute(allow_cross_state: bool = False, scenario: dict = None) -> dict:
    """scenario (emergency simulator): {"phc_ids": set, "drug_mult": {code: x}, "duration": days}
    scales forecast demand at those PHCs for `duration` days (fading out over the next week),
    then re-runs early warning and redistribution. The stored data is never changed."""
    t0 = time.perf_counter()
    phcs, districts, states, stock_rows, foot_rows, transfers = load()
    today = config.TODAY
    first = min(date.fromisoformat(r["day"]) for r in foot_rows)
    T = (today - first).days + 1
    days = [first + timedelta(days=t) for t in range(T)]
    N, D = len(phcs), len(DRUGS)
    pidx = {p["id"]: n for n, p in enumerate(phcs)}
    didx = {c: j for j, c in enumerate(DRUG_CODES)}

    demand = np.full((N, D, T), np.nan)
    closing = np.full((N, D, T), np.nan)
    for r in stock_rows:
        t = (date.fromisoformat(r["day"]) - first).days
        i, j = pidx[r["phc_id"]], didx[r["drug_code"]]
        closing[i, j, t] = r["closing"]
        if r["dispensed"] is not None:          # rows opened only by a transfer carry no demand
            demand[i, j, t] = r["dispensed"] + (r["unmet"] or 0)
    foot = {k: np.full((N, T), np.nan) for k in ("opd", "fever", "diarrhoea", "respiratory",
                                                  "beds_occupied", "staff_present")}
    for r in foot_rows:
        t = (date.fromisoformat(r["day"]) - first).days
        i = pidx[r["phc_id"]]
        for k in foot:
            if r[k] is not None:
                foot[k][i, t] = r[k]

    # ---- forecasting ---------------------------------------------------------------------
    S = N * D
    y = demand.reshape(S, T)
    hw = forecasting.fit(y)
    close2 = closing.reshape(S, T)
    has = ~np.isnan(close2)
    last_stock_t = np.where(has.any(axis=1), T - 1 - np.argmax(has[:, ::-1], axis=1), 0)
    last_demand_t = np.where((~np.isnan(y)).any(axis=1),
                             T - 1 - np.argmax((~np.isnan(y))[:, ::-1], axis=1), 0)
    H = config.FORECAST_HORIZON + 2
    fc = hw.forecast(last_demand_t, H)                    # from last observed demand day
    sigma = hw.sigma(last_demand_t)
    cur_stock = close2[np.arange(S), last_stock_t]

    # ---- anomalies (needed for outbreak-aware forecast adjustment) ------------------------
    wday = np.array([d.weekday() for d in days])
    foot_has = ~np.isnan(foot["opd"])
    last_foot_t = np.where(foot_has.any(axis=1), T - 1 - np.argmax(foot_has[:, ::-1], axis=1), 0)
    # Silent PHCs: their last numbers are too old to raise outbreak signals or move medicine on.
    days_silent = (T - 1) - last_foot_t
    stale = days_silent >= config.STALE_DAYS
    anom = anomaly.detect(foot, wday, last_foot_t, phcs, days, active=~stale)
    surge = np.ones(S)
    surge_reason = [None] * S
    for a in anom["anomalies"]:
        for dc in SYNDROME_DRUGS.get(a["syndrome"], []):
            s = pidx[a["phc_id"]] * D + didx[dc]
            t = last_demand_t[s]
            recent = np.nanmean(y[s, max(0, t - 2): t + 1])
            pred = np.nanmean(hw.yhat[s, max(0, t - 2): t + 1]) + 0.1
            f = float(np.clip(recent / pred, 1.0, 3.0))
            if f > surge[s]:
                surge[s], surge_reason[s] = f, f"{a['syndrome']} anomaly (x{a['ratio']})"
    decay = np.clip(1 - (np.arange(H) - 14) / 14, 0, 1)            # hold 14 days, fade by day 28
    fc_adj = fc * (1 + (surge[:, None] - 1) * decay[None, :])
    if scenario:
        ramp = np.clip(1 - (np.arange(H) - scenario["duration"]) / 7, 0, 1)
        mult = np.ones(S)
        for pid in scenario["phc_ids"]:
            if pid in pidx:
                for code, m in scenario["drug_mult"].items():
                    mult[pidx[pid] * D + didx[code]] = m
        fc_adj = fc_adj * (1 + (mult[:, None] - 1) * ramp[None, :])

    # ---- pipeline from transfers -----------------------------------------------------------
    incoming = np.zeros(S)          # approved / in transit, not yet received
    committed = np.zeros(S)         # approved, not yet dispatched (still on donor's shelf)
    for tr in transfers:
        if tr["status"] not in ("approved", "in_transit"):
            continue
        for ln in json.loads(tr["lines_json"]):
            j = didx[ln["drug_code"]]
            incoming[pidx[tr["to_phc"]] * D + j] += ln["qty"]
            if tr["status"] == "approved":
                committed[pidx[tr["from_phc"]] * D + j] += ln["qty"]

    # ---- stock projection -------------------------------------------------------------------
    # Projection starts the day after the last stock count; express in days from today.
    elapsed = np.array([(today - days[t]).days for t in last_stock_t])
    avail = cur_stock + incoming - committed
    dts_raw = forecasting.days_until_cumulative(fc_adj, np.maximum(avail, 0))
    dts = dts_raw - elapsed                          # days from today
    anchors = [date.fromisoformat(p["supply_anchor"]) for p in phcs]
    supply_in = np.repeat([_next_supply_days(a, today) for a in anchors], D).astype(float)
    daily = fc_adj[:, :7].mean(axis=1)
    cover = np.where(daily > 0.01, np.maximum(avail, 0) / np.maximum(daily, 1e-6), 999)
    # P(stock-out before next delivery): normal approx on cumulative demand to that day
    hsup = np.clip(supply_in + elapsed, 1, H).astype(int)
    cum_to_supply = np.cumsum(fc_adj, axis=1)[np.arange(S), hsup - 1]
    sd = sigma * np.sqrt(hsup)
    from math import erf
    z = (np.maximum(avail, 0) - cum_to_supply) / np.maximum(sd, 1e-6)
    p_out = np.array([0.5 * (1 - erf(v / np.sqrt(2))) for v in z])

    status = np.full(S, "ok", dtype=object)
    before_supply = dts <= supply_in        # a same-day stock-out still counts
    w = config.WARNING_WINDOW
    status[(dts <= w) & before_supply] = "watch"
    status[(dts <= 14) & before_supply] = "high"
    status[(dts <= 7) & before_supply] = "critical"
    status[avail <= 0] = "stocked_out"
    # surplus: stock beyond (safety-factored) demand until next supply + 30 days
    need_to_supply = cum_to_supply * config.SAFETY_FACTOR + daily * config.SAFETY_DAYS
    surplus_units = np.maximum(avail - need_to_supply - daily * 30, 0)
    status[(status == "ok") & (surplus_units > np.maximum(daily * 10, 5))] = "surplus"

    # ---- redistribution ------------------------------------------------------------------------
    lat = np.array([p["lat"] for p in phcs]); lon = np.array([p["lon"] for p in phcs])
    road = distance_matrix_km(lat, lon) * config.ROAD_FACTOR
    deficits, donors = [], []
    for s in range(S):
        i, j = divmod(s, D)
        if stale[i]:          # verify by phone first; see "stale" on the PHC
            continue
        if status[s] in ("critical", "high", "watch", "stocked_out"):
            horizon = int(min(supply_in[s] + elapsed[s] + config.SAFETY_DAYS, H))
            need = float(np.ceil(fc_adj[s, :horizon].sum() - max(avail[s], 0)))
            if need >= 1:
                deficits.append({"phc_idx": i, "drug": DRUG_CODES[j], "need": need,
                                 "days_to_stockout": int(max(dts[s], 0)),
                                 # days the shelf would stand empty before the next delivery
                                 "gap_days": float(max(0.0, min(supply_in[s], H) - max(dts[s], 0)))})
        elif status[s] == "surplus":
            donors.append({"phc_idx": i, "drug": DRUG_CODES[j],
                           "surplus": float(np.floor(surplus_units[s]))})
    plan = redistribution.optimise(deficits, donors, phcs, road, allow_cross_state)
    impact = _impact(plan, deficits, phcs)

    # ---- per-PHC summaries & resilience score -----------------------------------------------
    anoms_by_phc = {}
    for a in anom["anomalies"]:
        anoms_by_phc.setdefault(a["phc_id"], []).append(a)
    t_today = T - 1
    phc_summ = []
    for i, p in enumerate(phcs):
        sl = slice(i * D, (i + 1) * D)
        st = status[sl]
        lt = int(last_foot_t[i])
        beds = foot["beds_occupied"][i, lt]
        staff = foot["staff_present"][i, lt]
        reported_today = lt == t_today
        crit = int(np.isin(st, ["critical", "stocked_out"]).sum())
        high = int((st == "high").sum()); watch = int((st == "watch").sum())
        a_list = anoms_by_phc.get(p["id"], [])
        score = 100 - 18 * crit - 8 * high - 3 * watch
        score -= sum(15 if a["in_cluster"] else 8 for a in a_list)
        occ = float(beds / p["beds_total"]) if not np.isnan(beds) else None
        att = float(staff / p["staff_sanctioned"]) if not np.isnan(staff) else None
        if occ is not None and occ >= 0.9: score -= 8
        if att is not None and att < 0.6: score -= 8
        if not reported_today: score -= 5
        score = int(max(0, min(100, score)))
        phc_summ.append({
            **{k: p[k] for k in ("id", "code", "name", "block", "district_code", "state_code",
                                  "lat", "lon", "beds_total", "staff_sanctioned", "is_24x7",
                                  "language", "nin")},
            "last_report": days[lt].isoformat(), "reported_today": bool(reported_today),
            "days_since_report": int(days_silent[i]), "stale": bool(stale[i]),
            "opd_last": None if np.isnan(foot["opd"][i, lt]) else int(foot["opd"][i, lt]),
            "beds_occupied": None if np.isnan(beds) else int(beds),
            "bed_occupancy": occ, "staff_present": None if np.isnan(staff) else int(staff),
            "attendance": att, "critical_items": crit, "high_items": high, "watch_items": watch,
            "surplus_items": int((st == "surplus").sum()), "anomalies": len(a_list),
            "score": score,
            "health": "red" if score < 55 else ("amber" if score < 80 else "green"),
            "next_supply_in": int(supply_in[i * D]),
        })

    items = []
    for s in range(S):
        i, j = divmod(s, D)
        items.append({
            "phc_id": phcs[i]["id"], "drug_code": DRUG_CODES[j], "stock": float(cur_stock[s]),
            "incoming": float(incoming[s]), "committed": float(committed[s]),
            "daily_forecast": round(float(daily[s]), 2), "cover_days": round(float(min(cover[s], 999)), 1),
            "days_to_stockout": None if not np.isfinite(dts[s]) else int(dts[s]),
            "next_supply_in": int(supply_in[s]), "p_stockout": round(float(p_out[s]), 3),
            "status": status[s], "surplus_units": float(np.floor(surplus_units[s])),
            "surge": round(float(surge[s]), 2), "surge_reason": surge_reason[s],
            "stale": bool(stale[i]),
        })

    # ---- backtest (model credibility panel) -------------------------------------------------
    supply_days_hist = np.zeros((S, T))
    for i, a in enumerate(anchors):
        sup = np.array([_next_supply_days(a, d) for d in days], dtype=float)
        supply_days_hist[i * D:(i + 1) * D] = sup
    bt = None if scenario else forecasting.backtest(y, np.nan_to_num(close2, nan=1e9), hw,
                                                        supply_days_hist, T - 2)

    return {
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "compute_ms": round((time.perf_counter() - t0) * 1000),
        "today": today.isoformat(), "days": [d.isoformat() for d in days],
        "phcs": phc_summ, "items": items, "districts": districts, "states": states,
        "anomalies": anom["anomalies"], "clusters": anom["clusters"],
        "plan": _decorate_plan(plan, phcs), "backtest": bt, "allow_cross_state": allow_cross_state,
        "impact": impact,
        "_arrays": {"demand": demand, "closing": closing, "fc": fc_adj.reshape(N, D, H),
                    "sigma": sigma.reshape(N, D), "foot": foot, "wday": wday,
                    "wf": anom["weekday_factors"], "last_foot_t": last_foot_t,
                    "last_demand_t": last_demand_t.reshape(N, D),
                    "last_stock_t": last_stock_t.reshape(N, D), "pidx": pidx, "didx": didx},
    }


def _impact(plan: dict, deficits: list, phcs: list) -> dict:
    """What the current transfer plan achieves, in terms a ministry can weigh. Prices and
    emergency-procurement costs are indicative assumptions (see reference.py / config.py)."""
    by_key = {(d["phc_idx"], d["drug"]): d for d in deficits}
    prevented, units, value, lifesaving, patients = 0.0, 0.0, 0.0, 0, 0.0
    lines = 0
    for sh in plan["shipments"]:
        for ln in sh["lines"]:
            d = by_key.get((sh["to_idx"], ln["drug_code"]))
            if d is None:
                continue
            frac = min(1.0, ln["qty"] / max(d["need"], 1e-9))
            # Kept on the line so any jurisdiction's impact is a sum over its own transfers.
            ln["prevented_days"] = d["gap_days"] * frac
            prevented += ln["prevented_days"]
            units += ln["qty"]
            value += ln["qty"] * DRUG_BY_CODE[ln["drug_code"]]["price_inr"]
            patients += ln["qty"] / DRUG_BY_CODE[ln["drug_code"]]["units_per_patient"]
            lifesaving += ln["drug_code"] in LIFE_SAVING
            lines += 1
    transport = float(sum(s["cost_inr"] for s in plan["shipments"]))
    return impact_summary(prevented, units, value, patients, lifesaving, lines, transport, len(phcs))


def impact_summary(prevented, units, value, patients, lifesaving, lines, transport, n_phcs) -> dict:
    # Without a transfer each line becomes an emergency indent or local purchase at a premium.
    emergency = value * config.EMERGENCY_PREMIUM + lines * config.EMERGENCY_INDENT_COST
    n = n_phcs or 1
    return {"stockout_days_prevented": round(prevented), "units_moved": round(units),
            "patients_covered": round(patients), "medicine_value_inr": round(value),
            "transport_cost_inr": round(transport), "emergency_cost_avoided_inr": round(emergency),
            "net_saving_inr": round(emergency - transport), "lifesaving_lines": lifesaving,
            "phcs": n_phcs,
            "national_projection": {  # linear scale-up per monthly supply cycle, clearly an estimate
                "phcs": config.INDIA_PHCS,
                "stockout_days_prevented": round(prevented / n * config.INDIA_PHCS),
                "patients_covered": round(patients / n * config.INDIA_PHCS),
                "net_saving_inr": round((emergency - transport) / n * config.INDIA_PHCS)}}


def impact_for(shipments: list, n_phcs: int) -> dict:
    """Impact of a subset of the plan (e.g. one district's transfers)."""
    lines = [ln for s in shipments for ln in s["lines"] if "prevented_days" in ln]
    return impact_summary(
        sum(ln["prevented_days"] for ln in lines), sum(ln["qty"] for ln in lines),
        sum(ln["qty"] * DRUG_BY_CODE[ln["drug_code"]]["price_inr"] for ln in lines),
        sum(ln["qty"] / DRUG_BY_CODE[ln["drug_code"]]["units_per_patient"] for ln in lines),
        sum(ln["drug_code"] in LIFE_SAVING for ln in lines), len(lines),
        float(sum(s["cost_inr"] for s in shipments)), n_phcs)


def _decorate_plan(plan: dict, phcs: list) -> dict:
    def ref(idx):
        p = phcs[idx]
        return {"id": p["id"], "code": p["code"], "name": p["name"],
                "district_code": p["district_code"], "state_code": p["state_code"],
                "lat": p["lat"], "lon": p["lon"]}
    for s in plan["shipments"]:
        s["from"], s["to"] = ref(s.pop("from_idx")), ref(s.pop("to_idx"))
    for e in plan["escalations"]:
        e["phc"] = ref(e.pop("phc_idx"))
    return plan

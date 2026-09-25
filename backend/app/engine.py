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
from .reference import DRUGS

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


def compute(allow_cross_state: bool = False) -> dict:
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
    anom = anomaly.detect(foot, wday, last_foot_t, phcs, days)
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
        if status[s] in ("critical", "high", "watch", "stocked_out"):
            horizon = int(min(supply_in[s] + elapsed[s] + config.SAFETY_DAYS, H))
            need = float(np.ceil(fc_adj[s, :horizon].sum() - max(avail[s], 0)))
            if need >= 1:
                deficits.append({"phc_idx": i, "drug": DRUG_CODES[j], "need": need,
                                 "days_to_stockout": int(max(dts[s], 0))})
        elif status[s] == "surplus":
            donors.append({"phc_idx": i, "drug": DRUG_CODES[j],
                           "surplus": float(np.floor(surplus_units[s]))})
    plan = redistribution.optimise(deficits, donors, phcs, road, allow_cross_state)

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
        })

    # ---- backtest (model credibility panel) -------------------------------------------------
    supply_days_hist = np.zeros((S, T))
    for i, a in enumerate(anchors):
        sup = np.array([_next_supply_days(a, d) for d in days], dtype=float)
        supply_days_hist[i * D:(i + 1) * D] = sup
    bt = forecasting.backtest(y, np.nan_to_num(close2, nan=1e9), hw, supply_days_hist, T - 2)

    return {
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "compute_ms": round((time.perf_counter() - t0) * 1000),
        "today": today.isoformat(), "days": [d.isoformat() for d in days],
        "phcs": phc_summ, "items": items, "districts": districts, "states": states,
        "anomalies": anom["anomalies"], "clusters": anom["clusters"],
        "plan": _decorate_plan(plan, phcs), "backtest": bt, "allow_cross_state": allow_cross_state,
        "_arrays": {"demand": demand, "closing": closing, "fc": fc_adj.reshape(N, D, H),
                    "sigma": sigma.reshape(N, D), "foot": foot, "wday": wday,
                    "wf": anom["weekday_factors"], "last_foot_t": last_foot_t,
                    "last_demand_t": last_demand_t.reshape(N, D),
                    "last_stock_t": last_stock_t.reshape(N, D), "pidx": pidx, "didx": didx},
    }


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

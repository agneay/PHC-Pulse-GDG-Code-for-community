"""National-scale benchmark: run the PHC Pulse engine on a synthetic network the size of India.

24,935 PHCs (Rural Health Statistics 2021-22) x 10 drugs = ~250,000 forecast series, split
across 36 states/UTs roughly in proportion to rural population. Each state is processed on its
own, exactly as in production (the MILP decomposes by state, and federated training keeps data
in the state), so the states could run in parallel; we time them sequentially on one machine.

Stages timed per state: demand forecasting (Holt-Winters, 120 days of history, 30-day horizon),
stock-out early warning, outbreak anomaly detection, and the redistribution MILP.

    cd backend && python ../scripts/scale_benchmark.py            # full size (a few minutes)
    cd backend && python ../scripts/scale_benchmark.py --phcs 3000   # quick run

Writes backend/app/benchmarks/scale_benchmark.json, shown on the Models page.
"""
import argparse
import json
import os
import platform
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app import anomaly, config, forecasting, redistribution  # noqa: E402
from app.geo import distance_matrix_km  # noqa: E402
from app.reference import DRUGS  # noqa: E402

# (code, approx. centroid lat, lon, share weight ~ rural population)
STATES = [("UP", 26.8, 80.9, 155), ("BR", 25.6, 85.1, 92), ("MH", 19.7, 75.7, 61), ("WB", 23.0, 87.9, 62),
          ("MP", 23.5, 78.0, 53), ("RJ", 26.6, 73.8, 52), ("TN", 11.1, 78.7, 37), ("KA", 15.3, 75.7, 38),
          ("GJ", 22.3, 71.2, 35), ("AP", 15.9, 79.7, 35), ("OD", 20.5, 84.7, 35), ("TG", 17.9, 79.0, 21),
          ("KL", 10.5, 76.3, 17), ("JH", 23.6, 85.3, 25), ("AS", 26.2, 92.9, 27), ("PB", 31.1, 75.3, 17),
          ("CG", 21.3, 81.9, 20), ("HR", 29.1, 76.1, 17), ("JK", 33.8, 75.0, 9), ("UK", 30.1, 79.0, 7),
          ("HP", 31.8, 77.2, 6), ("TR", 23.8, 91.4, 3), ("ML", 25.5, 91.4, 2.4), ("MN", 24.7, 93.9, 2),
          ("NL", 26.2, 94.5, 1.4), ("GA", 15.4, 74.0, 0.6), ("AR", 28.2, 94.7, 1.1), ("MZ", 23.2, 92.9, 0.5),
          ("SK", 27.5, 88.5, 0.5), ("DL", 28.6, 77.2, 0.4), ("PY", 11.9, 79.8, 0.4), ("CH", 30.7, 76.8, 0.1),
          ("AN", 11.7, 92.7, 0.3), ("DD", 20.4, 72.8, 0.3), ("LA", 34.2, 77.6, 0.2), ("LD", 10.6, 72.6, 0.1)]
HISTORY, HORIZON = 120, 30
D = len(DRUGS)
DRUG_CODES = [d["code"] for d in DRUGS]


def synth_state(code, lat0, lon0, n, rng):
    spread = max(0.3, min(2.5, np.sqrt(n) / 18))
    phcs = [{"id": k, "code": f"{code}-{k}", "name": f"PHC {code}-{k}", "district_code": f"{code}{k // 40}",
             "state_code": code, "lat": float(lat0 + rng.normal(0, spread)), "lon": float(lon0 + rng.normal(0, spread))}
            for k in range(n)]
    today = config.TODAY
    days = [today - timedelta(days=HISTORY - 1 - t) for t in range(HISTORY)]
    wday = np.array([d.weekday() for d in days])
    wk = np.array([1.25, 1.1, 1.0, 1.0, 0.95, 0.9, 0.55])[wday]
    opd = rng.gamma(6, 9, size=(n, 1)) * wk[None, :] * rng.lognormal(0, 0.12, size=(n, HISTORY))
    rate = np.array([d["rate"] for d in DRUGS])
    demand = rng.poisson(opd[:, None, :] * rate[None, :, None]).astype(float)       # (n, D, T)
    demand[rng.random(demand.shape) < 0.04] = np.nan                                 # missed reports
    foot = {"opd": opd.round(), "fever": (opd * 0.2).round(), "diarrhoea": (opd * 0.08).round(),
            "respiratory": (opd * 0.12).round()}
    spike = rng.choice(n, size=max(1, n // 200), replace=False)                      # a few outbreaks
    foot["diarrhoea"][spike, -3:] *= 4
    stock = demand[:, :, -30:].copy()
    stock = np.nansum(stock, axis=2) * rng.uniform(0.2, 2.2, size=(n, D))            # varied cover
    supply_in = rng.integers(1, 31, size=n)
    return phcs, days, wday, demand, foot, stock, supply_in


def run_state(code, lat0, lon0, n, rng):
    phcs, days, wday, demand, foot, stock, supply_in = synth_state(code, lat0, lon0, n, rng)
    t = {}
    s0 = time.perf_counter()
    y = demand.reshape(n * D, HISTORY)
    hw = forecasting.fit(y)
    last = np.full(n * D, HISTORY - 1)
    fc = hw.forecast(last, HORIZON)
    t["forecast_s"] = time.perf_counter() - s0

    s0 = time.perf_counter()
    avail = stock.reshape(-1)
    dts = forecasting.days_until_cumulative(fc, avail)
    sup = np.repeat(supply_in, D)
    at_risk = (dts <= sup) & (dts <= 21)
    daily = fc[:, :7].mean(axis=1)
    need_to_supply = np.cumsum(fc, axis=1)[np.arange(n * D), np.clip(sup, 1, HORIZON) - 1]
    surplus = np.maximum(avail - need_to_supply * config.SAFETY_FACTOR - daily * (config.SAFETY_DAYS + 30), 0)
    t["early_warning_s"] = time.perf_counter() - s0

    s0 = time.perf_counter()
    last_foot = np.full(n, HISTORY - 1)
    an = anomaly.detect(foot, wday, last_foot, phcs, days)
    t["anomaly_s"] = time.perf_counter() - s0

    s0 = time.perf_counter()
    lat = np.array([p["lat"] for p in phcs]); lon = np.array([p["lon"] for p in phcs])
    road = distance_matrix_km(lat, lon) * config.ROAD_FACTOR
    deficits, donors = [], []
    for s in np.flatnonzero(at_risk):
        i, j = divmod(int(s), D)
        need = float(np.ceil(fc[s, :min(int(sup[s]) + config.SAFETY_DAYS, HORIZON)].sum() - avail[s]))
        if need >= 1:
            deficits.append({"phc_idx": i, "drug": DRUG_CODES[j], "need": need, "days_to_stockout": int(max(dts[s], 0))})
    for s in np.flatnonzero((~at_risk) & (surplus > np.maximum(daily * 10, 5))):
        i, j = divmod(int(s), D)
        donors.append({"phc_idx": i, "drug": DRUG_CODES[j], "surplus": float(np.floor(surplus[s]))})
    plan = redistribution.optimise(deficits, donors, phcs, road, False)
    t["milp_s"] = time.perf_counter() - s0
    t = {k: round(v, 3) for k, v in t.items()}
    return {"state": code, "phcs": n, "series": n * D, "deficits": len(deficits), "donors": len(donors),
            "shipments": plan["stats"]["shipments"], "coverage": plan["stats"]["coverage"],
            "milp_variables": plan["stats"].get("variables"), "milp_time_limited": bool(plan["stats"].get("time_limited")),
            "anomalies": len(an["anomalies"]),
            "clusters": len(an["clusters"]), **t, "total_s": round(sum(t.values()), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phcs", type=int, default=config.INDIA_PHCS)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    w = np.array([s[3] for s in STATES]); counts = np.maximum(3, np.round(w / w.sum() * args.phcs)).astype(int)
    out = []
    t0 = time.perf_counter()
    for (code, lat, lon, _), n in zip(STATES, counts):
        r = run_state(code, lat, lon, int(n), rng)
        out.append(r)
        print(f"{code:3} {n:5} PHCs  forecast {r['forecast_s']:6.2f}s  milp {r['milp_s']:6.2f}s  total {r['total_s']:6.2f}s", flush=True)
    wall = time.perf_counter() - t0
    res = {
        "generated": date.today().isoformat(), "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs, "
        f"single process, Python {platform.python_version()}",
        "phcs": int(counts.sum()), "states": len(STATES), "series": int(counts.sum()) * D,
        "history_days": HISTORY, "horizon_days": HORIZON,
        "sequential_s": round(wall, 1), "slowest_state_s": max(r["total_s"] for r in out),
        "slowest_state": max(out, key=lambda r: r["total_s"])["state"],
        "stage_totals_s": {k: round(sum(r[k] for r in out), 1) for k in ("forecast_s", "early_warning_s", "anomaly_s", "milp_s")},
        "shipments": sum(r["shipments"] for r in out), "deficits": sum(r["deficits"] for r in out),
        "units_coverage": round(sum((r["coverage"] or 0) * r["deficits"] for r in out) / max(sum(r["deficits"] for r in out), 1), 3),
        "states_milp_time_limited": [r["state"] for r in out if r["milp_time_limited"]],
        "note": "Synthetic network sized to India's PHCs; states are independent, so with one worker per "
                "state the wall time is the slowest state.",
        "per_state": out,
    }
    path = Path(__file__).resolve().parent.parent / "backend" / "app" / "benchmarks" / "scale_benchmark.json"
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n{res['phcs']} PHCs, {res['series']} series: {res['sequential_s']}s sequential, "
          f"slowest state {res['slowest_state']} {res['slowest_state_s']}s -> {path}")


if __name__ == "__main__":
    main()

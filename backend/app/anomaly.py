"""Outbreak early-warning: footfall anomaly detection + spatial clustering.

For every PHC and syndrome (fever / diarrhoea / respiratory / total OPD) we compare the latest
days against a robust, weekday-adjusted baseline built from the previous 28 days
(median + MAD, floored by Poisson noise). A PHC-level anomaly needs z >= 3 *and* a
material excess. Anomalies of the same syndrome at >= 2 PHCs within 50 km over the last
3 days are escalated as a *cluster* - the early outbreak signal an IDSP officer acts on.
"""
import numpy as np

from .geo import haversine_km

SYNDROMES = ["fever", "diarrhoea", "respiratory", "opd"]
Z_THRESHOLD = 3.0
MIN_RATIO = 1.5
MIN_EXCESS = 5
CLUSTER_KM = 50.0
BASELINE_DAYS = 28


def weekday_factors(opd: np.ndarray, wday: np.ndarray) -> np.ndarray:
    """Per-PHC weekday multipliers from the last 90 days. opd: (N, T) -> (N, 7)"""
    x = opd[:, -90:]
    wd = wday[-90:]
    mean = np.nanmean(x, axis=1, keepdims=True) + 1e-6
    f = np.ones((opd.shape[0], 7))
    for w in range(7):
        cols = x[:, wd == w]
        if cols.size:
            f[:, w] = np.nanmean(cols, axis=1) / mean[:, 0]
    return np.clip(f, 0.2, 3.0)


def baseline(series: np.ndarray, wf: np.ndarray, wday: np.ndarray, t: int):
    """Expected value and robust scale for day t, per PHC. series: (N, T)."""
    lo = max(0, t - BASELINE_DAYS)
    past = series[:, lo:t] / wf[:, wday[lo:t]]
    med = np.nanmedian(past, axis=1)
    mad = np.nanmedian(np.abs(past - med[:, None]), axis=1)
    exp = med * wf[:, wday[t]]
    scale = np.maximum(1.4826 * mad * wf[:, wday[t]], np.sqrt(np.maximum(exp, 1.0)))
    return exp, scale


def detect(foot: dict, wday: np.ndarray, last_idx: np.ndarray, phcs: list, days: list) -> dict:
    """foot: {'opd','fever','diarrhoea','respiratory'} -> (N, T) arrays (NaN = no report).
    Returns PHC-level anomalies, clusters, and per-PHC expected bands for charts."""
    N, T = foot["opd"].shape
    wf = weekday_factors(foot["opd"], wday)
    anomalies = []
    for syn in SYNDROMES:
        s = foot[syn]
        for back in range(3):                          # last 3 reporting days per PHC
            t_arr = last_idx - back
            exp_all, sc_all = np.full(N, np.nan), np.full(N, np.nan)
            for t in np.unique(t_arr):                 # vectorise over PHCs sharing a day
                if t < BASELINE_DAYS:
                    continue
                m = t_arr == t
                exp_all[m], sc_all[m] = baseline(s[m], wf[m], wday, int(t))
            for i in range(N):
                t = int(t_arr[i])
                if t < BASELINE_DAYS or np.isnan(s[i, t]) or np.isnan(exp_all[i]):
                    continue
                x, e, sc = float(s[i, t]), float(exp_all[i]), float(sc_all[i])
                z = (x - e) / sc
                if z >= Z_THRESHOLD and x >= MIN_RATIO * e and x - e >= MIN_EXCESS:
                    anomalies.append({
                        "phc_id": phcs[i]["id"], "phc_code": phcs[i]["code"],
                        "phc_name": phcs[i]["name"], "district_code": phcs[i]["district_code"],
                        "state_code": phcs[i]["state_code"], "syndrome": syn,
                        "day": days[t].isoformat(), "observed": int(x), "expected": round(e, 1),
                        "ratio": round(x / max(e, 0.1), 2), "z": round(z, 1), "days_back": back,
                    })

    # Collapse to one record per PHC x syndrome (latest day), counting consecutive days.
    merged = {}
    for a in sorted(anomalies, key=lambda a: a["days_back"]):
        key = (a["phc_id"], a["syndrome"])
        if key not in merged:
            merged[key] = dict(a, consecutive_days=1)
        else:
            merged[key]["consecutive_days"] += 1
    phc_anoms = list(merged.values())
    # Total-OPD anomalies are only reported when no specific syndrome explains them.
    specific = {a["phc_id"] for a in phc_anoms if a["syndrome"] != "opd"}
    phc_anoms = [a for a in phc_anoms if a["syndrome"] != "opd" or a["phc_id"] not in specific]

    clusters = []
    by_syn = {}
    for a in phc_anoms:
        by_syn.setdefault((a["district_code"], a["syndrome"]), []).append(a)
    pos = {p["id"]: (p["lat"], p["lon"]) for p in phcs}
    for (dist, syn), items in by_syn.items():
        if len(items) < 2 or syn == "opd":
            continue
        members = [a for a in items if any(
            b is not a and haversine_km(*pos[a["phc_id"]], *pos[b["phc_id"]]) <= CLUSTER_KM
            for b in items)]
        if len(members) >= 2:
            lat = float(np.mean([pos[m["phc_id"]][0] for m in members]))
            lon = float(np.mean([pos[m["phc_id"]][1] for m in members]))
            clusters.append({
                "id": f"CL-{dist}-{syn}", "district_code": dist, "state_code": members[0]["state_code"],
                "syndrome": syn, "phc_ids": [m["phc_id"] for m in members],
                "phc_codes": [m["phc_code"] for m in members],
                "excess_cases": int(sum(m["observed"] - m["expected"] for m in members)),
                "max_ratio": max(m["ratio"] for m in members),
                "max_consecutive_days": max(m["consecutive_days"] for m in members),
                "lat": lat, "lon": lon, "severity": "high" if len(members) >= 3 else "medium",
            })
    in_cluster = {pid for c in clusters for pid in c["phc_ids"]}
    for a in phc_anoms:
        a["in_cluster"] = a["phc_id"] in in_cluster
        a["severity"] = "high" if a["in_cluster"] else ("medium" if a["z"] >= 4 else "low")
    phc_anoms.sort(key=lambda a: (-int(a["in_cluster"]), -a["z"]))
    return {"anomalies": phc_anoms, "clusters": clusters, "weekday_factors": wf}


def expected_band(series: np.ndarray, wf_row: np.ndarray, wday: np.ndarray, t_end: int, days: int = 60):
    """Rolling expected value / upper alert threshold for one PHC's series (for charts)."""
    out = []
    s = series[None, :]
    for t in range(max(BASELINE_DAYS, t_end - days + 1), t_end + 1):
        exp, sc = baseline(s, wf_row[None, :], wday, t)
        out.append((t, float(exp[0]), float(exp[0] + Z_THRESHOLD * sc[0])))
    return out

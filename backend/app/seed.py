"""Synthetic-but-realistic data generator for the prototype.

Simulates 180 days of daily PHC operations for 120 PHCs across 8 districts in 4 states:
  * OPD footfall with weekday pattern and monsoon seasonality per syndrome
    (fever / diarrhoea / respiratory), sized like HMIS PHC OPD volumes.
  * Per-drug demand driven by footfall, with state epidemiology (malaria in Odisha, snakebite
    in TN/KA, diarrhoea in UP) and monsoon effects.
  * Monthly indent-based replenishment from district warehouses with uneven supply
    (some PHCs chronically over-indented, others rationed) and partial / late deliveries,
    so real stock-outs AND idle surplus coexist, which is what redistribution needs.
  * Three injected outbreak signals for the anomaly detector.
  * The deck's walkthrough scenario: PHC-14 holds surplus paracetamol, PHC-22 runs out in ~9 days.
"""
import logging
import math
from datetime import timedelta

import numpy as np

from . import config
from .db import get_conn, init_schema
from .reference import DISTRICTS, DRUGS, STATE_DRUG_FACTOR, STATES

WEEKDAY_FACTOR = np.array([1.25, 1.10, 1.00, 1.00, 0.95, 0.90, 0.45])  # Mon..Sun
SYNDROME_SHARE = {"fever": 0.22, "diarrhoea": 0.09, "respiratory": 0.20}
OTHER_SHARE = 1.0 - sum(SYNDROME_SHARE.values())
log = logging.getLogger("phc.seed")


def _bump(doy: np.ndarray, center: int, width: float) -> np.ndarray:
    d = np.minimum(np.abs(doy - center), 365 - np.abs(doy - center))
    return np.exp(-0.5 * (d / width) ** 2)


def _season(doy: np.ndarray) -> dict:
    return {
        "fever": 1 + 0.45 * _bump(doy, 245, 35),        # post-monsoon fevers peak ~Sep
        "diarrhoea": 1 + 0.60 * _bump(doy, 205, 30),    # monsoon diarrhoea peak ~late Jul
        "respiratory": 1 + 0.25 * _bump(doy, 215, 45) + 0.4 * _bump(doy, 15, 30),
        "snake": 1 + 0.9 * _bump(doy, 200, 40),         # snakebites peak in the monsoon
    }


def build_phcs(rng):
    phcs = []
    idx = 1
    for d in DISTRICTS:
        state = next(s for s in STATES if s["code"] == d["state"])
        for b, block in enumerate(d["blocks"]):
            ang = rng.uniform(0, 2 * math.pi)
            rad = 0.08 + 0.32 * math.sqrt(rng.uniform())
            lat = d["lat"] + rad * math.sin(ang)
            lon = d["lon"] + rad * math.cos(ang) / math.cos(math.radians(d["lat"]))
            is247 = rng.uniform() < 0.4
            phcs.append({
                "id": idx, "code": f"PHC-{idx}", "name": f"PHC {block}", "block": block,
                "district_code": d["code"], "state_code": d["state"],
                "lat": round(lat, 4), "lon": round(lon, 4),
                "beds_total": 10 if is247 else 6, "staff_sanctioned": int(rng.integers(9, 15)),
                "is_24x7": int(is247), "language": state["language"],
                "nin": f"{2000000000 + idx * 7919}",
            })
            idx += 1
    # Walkthrough scenario pins: PHC-14 (Villupuram) and PHC-22 (Tiruvannamalai) ~40 km apart.
    phcs[13].update(lat=12.212, lon=79.612)
    phcs[21].update(lat=12.498, lon=79.585)
    return phcs


def simulate(rng, phcs):
    N, D, T = len(phcs), len(DRUGS), config.HISTORY_DAYS
    today = config.TODAY
    days = [today - timedelta(days=T - 1 - t) for t in range(T)]
    doy = np.array([d.timetuple().tm_yday for d in days])
    wday = np.array([d.weekday() for d in days])
    season = _season(doy)
    wk = WEEKDAY_FACTOR[wday]                                   # (T,)

    base = rng.uniform(35, 110, size=N)                         # mean weekday OPD
    # ---- footfall -----------------------------------------------------------------------
    lam = {k: base[:, None] * share * wk[None, :] * season[k][None, :]
           for k, share in SYNDROME_SHARE.items()}
    other_lam = base[:, None] * OTHER_SHARE * wk[None, :]

    # Injected outbreak signals: multipliers on syndrome intensity.
    outbreak = {k: np.ones((N, T)) for k in SYNDROME_SHARE}
    by_code = {p["code"]: p for p in phcs}

    def nearest(district_code, k):
        ps = [p for p in phcs if p["district_code"] == district_code]
        c = ps[0]
        ps.sort(key=lambda p: (p["lat"] - c["lat"]) ** 2 + (p["lon"] - c["lon"]) ** 2)
        return [p["id"] - 1 for p in ps[:k]]

    # 1) Acute diarrhoeal disease cluster in Koraput (post-flood water contamination).
    ramp = np.array([1.8, 2.6, 3.4, 4.0, 4.6, 5.2])
    for i in nearest("KRP", 4):
        outbreak["diarrhoea"][i, T - len(ramp):] = ramp * rng.uniform(0.85, 1.15)
    # 2) Febrile illness cluster in Gorakhpur (AES / dengue season).
    ramp = np.array([1.6, 2.0, 2.4, 2.8, 3.0])
    for i in nearest("GKP", 3):
        outbreak["fever"][i, T - len(ramp):] = ramp * rng.uniform(0.9, 1.1)
    # 3) Isolated respiratory spike at a single Kalaburagi PHC (not a cluster).
    lone = nearest("KLB", 1)[0] + 5
    outbreak["respiratory"][lone, T - 2:] = [2.6, 3.1]

    counts = {k: rng.poisson(lam[k] * outbreak[k]) for k in lam}
    other = rng.poisson(other_lam)
    opd = other + sum(counts.values())

    beds_total = np.array([p["beds_total"] for p in phcs])
    occ_rate = 0.035 * (1 + 0.5 * (outbreak["diarrhoea"] - 1) + 0.3 * (outbreak["fever"] - 1))
    beds_occ = np.minimum(rng.poisson(opd * occ_rate), beds_total[:, None])
    staff_s = np.array([p["staff_sanctioned"] for p in phcs])
    attend = rng.beta(14, 3, size=(N, T)) * np.where(wday[None, :] == 6, 0.6, 1.0)
    staff_present = np.minimum(np.round(staff_s[:, None] * attend), staff_s[:, None])

    # ---- drug demand ----------------------------------------------------------------------
    demand = np.zeros((N, D, T))
    state_codes = [p["state_code"] for p in phcs]
    for j, drug in enumerate(DRUGS):
        sf = np.array([STATE_DRUG_FACTOR.get(s, {}).get(drug["code"], 1.0) for s in state_codes])
        syn = drug["syndrome"]
        if syn:
            driver = counts[syn] / SYNDROME_SHARE[syn]
        else:
            driver = base[:, None] * wk[None, :] * np.ones((N, T))
            if drug["code"] == "ASV":
                driver = driver * season["snake"][None, :]
        demand[:, j, :] = rng.poisson(drug["rate"] * sf[:, None] * driver)

    # ---- stock ledger with monthly indents -----------------------------------------------
    cycle = config.SUPPLY_CYCLE_DAYS
    phase = rng.integers(0, cycle, size=N)
    phase[21] = (T - 1 - 10) % cycle      # PHC-22 was supplied 10 days ago -> next in ~20 days
    phase[13] = (T - 1 - 3) % cycle       # PHC-14 was supplied 3 days ago
    avg_dem = demand[:, :, :28].mean(axis=2) + 0.05                 # what the indent is based on
    bias = np.clip(rng.lognormal(0.05, 0.27, size=(N, D)), 0.62, 2.3)  # indent / rationing skew
    bias[13, 0] = 3.2                                                # PHC-14 over-indents PCM
    bias[21, 0] = 0.8
    target = (cycle + 18) * avg_dem * bias

    stock = 40 * avg_dem * bias
    rows_stock = np.zeros((N, D, T, 6))  # opening, received, dispensed, unmet, adjustment, closing
    delay = np.full(N, -1)                # countdown for late deliveries
    for t in range(T):
        scheduled = ((t - phase) % cycle == 0)
        late = scheduled & (rng.uniform(size=N) < 0.15)
        delay[late] = rng.integers(2, 6, size=late.sum())
        due = scheduled & ~late
        due |= (delay == 0)
        delay[delay >= 0] -= 1
        partial = np.where(rng.uniform(size=(N, D)) < 0.12, 0.5, 1.0)
        received = np.where(due[:, None], np.maximum(0, target - stock) * partial, 0.0)
        received = np.round(received)
        opening = stock
        avail = opening + received
        disp = np.minimum(avail, demand[:, :, t])
        unmet = demand[:, :, t] - disp
        closing = avail - disp
        rows_stock[:, :, t] = np.stack(
            [opening, received, disp, unmet, np.zeros_like(opening), closing], axis=-1)
        stock = closing

    # ---- walkthrough pins via physical-count adjustment on the last day ---------------
    def pin_stock(i, j, cover_days):
        rate = demand[i, j, -28:].mean()
        want = round(rate * cover_days)
        rec = rows_stock[i, j, T - 1]
        rec[4] = want - rec[5]
        rec[5] = want

    pin_stock(21, 0, 8.6)     # PHC-22: runs out of paracetamol in ~9 days
    pin_stock(13, 0, 140.0)   # PHC-14: large paracetamol surplus

    # Which PHCs have already filed today's report (the rest are still due).
    reported_today = rng.uniform(size=N) < 0.68
    reported_today[[13, 21]] = True

    return {
        "days": days, "opd": opd, "counts": counts, "beds_occ": beds_occ,
        "staff_present": staff_present, "stock": rows_stock, "phase": phase,
        "reported_today": reported_today,
    }


def seed_database(force: bool = False) -> None:
    with get_conn() as conn:
        init_schema(conn)
        if not force and conn.execute("SELECT COUNT(*) FROM phcs").fetchone()[0] > 0:
            seeded_to = conn.execute(
                "SELECT MAX(day) FROM footfall_daily WHERE source='hmis'").fetchone()[0]
            if not config.RESEED_IF_STALE or seeded_to == config.TODAY.isoformat():
                return
            log.info("synthetic history ends %s but today is %s: re-seeding", seeded_to, config.TODAY)
        for tbl in ("states", "districts", "phcs", "drugs", "stock_daily", "footfall_daily",
                    "workers", "reports", "transfers"):
            conn.execute(f"DELETE FROM {tbl}")

        rng = np.random.default_rng(config.SEED)
        phcs = build_phcs(rng)
        sim = simulate(rng, phcs)
        days = sim["days"]
        T = len(days)

        conn.executemany("INSERT INTO states VALUES (?,?,?)",
                         [(s["code"], s["name"], s["language"]) for s in STATES])
        conn.executemany("INSERT INTO districts VALUES (?,?,?,?,?)",
                         [(d["code"], d["state"], d["name"], d["lat"], d["lon"]) for d in DISTRICTS])
        conn.executemany("INSERT INTO drugs VALUES (?,?,?)",
                         [(d["code"], d["name"], d["unit"]) for d in DRUGS])
        for i, p in enumerate(phcs):
            anchor = days[0] + timedelta(days=int(sim["phase"][i]))
            conn.execute(
                "INSERT INTO phcs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["id"], p["code"], p["name"], p["block"], p["district_code"], p["state_code"],
                 p["lat"], p["lon"], p["beds_total"], p["staff_sanctioned"], p["is_24x7"],
                 p["language"], anchor.isoformat(), p["nin"]))

        # Workers registry for USSD / IVR caller-ID lookup (one ASHA/ANM per PHC).
        conn.executemany("INSERT INTO workers VALUES (?,?,?,?,?)", [
            (f"+9190000{p['id']:05d}", f"ANM {p['block']}", "anm", p["id"], p["language"])
            for p in phcs])

        stock_rows, foot_rows = [], []
        for i, p in enumerate(phcs):
            last_t = T if sim["reported_today"][i] else T - 1
            for t in range(last_t):
                day = days[t].isoformat()
                foot_rows.append((
                    p["id"], day, int(sim["opd"][i, t]), int(sim["counts"]["fever"][i, t]),
                    int(sim["counts"]["diarrhoea"][i, t]), int(sim["counts"]["respiratory"][i, t]),
                    int(sim["beds_occ"][i, t]), int(sim["staff_present"][i, t]), "hmis"))
                for j, drug in enumerate(DRUGS):
                    o, r, ds, u, a, c = sim["stock"][i, j, t]
                    stock_rows.append((p["id"], drug["code"], day, float(o), float(r), float(ds),
                                       float(u), float(a), float(c), "hmis"))
        conn.executemany("INSERT INTO footfall_daily VALUES (?,?,?,?,?,?,?,?,?)", foot_rows)
        conn.executemany("INSERT INTO stock_daily VALUES (?,?,?,?,?,?,?,?,?,?)", stock_rows)


if __name__ == "__main__":
    seed_database(force=True)
    print("seeded", config.DB_PATH)

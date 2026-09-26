"""Federated forecasting across states: shared predictive modelling without pooling raw data.

Each state trains its own forecaster on its own PHC data ("local training"). Only a small model
update leaves the state:
  * the tuned smoothing constants (alpha, gamma, phi),
  * per drug, the weekday demand pattern (7 factors) and demand per 100 OPD patients,
  * how many observations the update was learned from.
The national server combines the updates with a sample-weighted average (FedAvg) into a shared
prior. A newly onboarded state, or a PHC with only a few days of history, starts from that prior
instead of guessing from almost no data.

`evaluate()` measures this honestly with leave-one-state-out: for each state the prior is built
from the *other* states only, and the state is treated as newly onboarded with 7 days of history.
"""
import time

import numpy as np

from . import forecasting
from .reference import DRUGS

DRUG_CODES = [d["code"] for d in DRUGS]
HOLDOUT = 28                 # days used to score a model
COLD_START_DAYS = 7          # history a newly onboarded state is assumed to have
GRID = [{"alpha": a, "beta": 0.04, "gamma": g, "phi": p}
        for a in (0.1, 0.25, 0.4) for g in (0.05, 0.15, 0.3) for p in (0.85, 0.95)]

_cache = {"key": None, "value": None}


def _wmape(fc: np.ndarray, actual: np.ndarray) -> float:
    m = ~np.isnan(actual)
    return float(np.abs(fc - np.nan_to_num(actual))[m].sum() / max(np.nan_to_num(actual)[m].sum(), 1e-9))


def _score(y: np.ndarray, params: dict, season0=None) -> float:
    """Fit on everything except the last HOLDOUT days, score the HOLDOUT-day forecast."""
    T = y.shape[1]
    hw = forecasting.fit(y[:, :T - HOLDOUT], params, season0)
    fc = hw.forecast(np.full(y.shape[0], T - HOLDOUT - 1), HOLDOUT)
    return _wmape(fc, y[:, T - HOLDOUT:])


def local_update(y: np.ndarray, drug_idx: np.ndarray, opd: np.ndarray, first_weekday: int) -> dict:
    """What one state computes on its own data and shares. y: (S, T) demand for the state's
    PHC x drug series; drug_idx: (S,) drug of each series; opd: (S, T) the PHC's OPD per series;
    first_weekday: calendar weekday (Mon=0) of day 0, so shared patterns are by calendar weekday."""
    scored = [(_score(y, p), p) for p in GRID]
    best_wmape, best = min(scored, key=lambda x: x[0])
    hw = forecasting.fit(y, best)
    # The model indexes weekday factors by day offset (t % 7); share them by calendar weekday.
    by_offset = hw.season[:, -1, :]                                      # (S, 7) final factors
    season_last = np.empty_like(by_offset)
    for k in range(7):
        season_last[:, (first_weekday + k) % 7] = by_offset[:, k]
    drugs = {}
    for j, code in enumerate(DRUG_CODES):
        m = drug_idx == j
        if not m.any():
            continue
        prof = season_last[m].mean(axis=0)
        prof = prof / prof.mean()
        both = ~np.isnan(y[m]) & ~np.isnan(opd[m])
        rate = 100 * y[m][both].sum() / max(opd[m][both].sum(), 1e-9)
        drugs[code] = {"weekday": [round(float(v), 4) for v in prof], "per_100_opd": round(float(rate), 3)}
    return {"params": {k: best[k] for k in ("alpha", "beta", "gamma", "phi")},
            "holdout_accuracy": round(1 - best_wmape, 3),
            "default_accuracy": round(1 - _score(y, forecasting.DEFAULT_PARAMS), 3),
            "drugs": drugs, "n_obs": int((~np.isnan(y)).sum()), "series": int(y.shape[0])}


def aggregate(updates: dict) -> dict:
    """FedAvg: sample-weighted average of the states' updates -> national prior."""
    w = {s: u["n_obs"] for s, u in updates.items()}
    tot = sum(w.values()) or 1
    params = {k: round(sum(u["params"][k] * w[s] for s, u in updates.items()) / tot, 4)
              for k in ("alpha", "beta", "gamma", "phi")}
    drugs = {}
    for code in DRUG_CODES:
        have = {s: u["drugs"][code] for s, u in updates.items() if code in u["drugs"]}
        if not have:
            continue
        ws = sum(w[s] for s in have) or 1
        prof = np.sum([np.array(d["weekday"]) * w[s] for s, d in have.items()], axis=0) / ws
        prof = prof / prof.mean()
        drugs[code] = {"weekday": [round(float(v), 4) for v in prof],
                       "per_100_opd": round(sum(d["per_100_opd"] * w[s] for s, d in have.items()) / ws, 3)}
    return {"params": params, "drugs": drugs, "states": sorted(updates), "n_obs": tot}


def _cold_start(y, drug_idx, opd, prior, first_weekday: int) -> dict:
    """Treat the state as newly onboarded: only COLD_START_DAYS of history before the holdout."""
    T = y.shape[1]
    c = T - HOLDOUT                                   # first day of the evaluation window
    win = slice(c - COLD_START_DAYS, c)
    y_win, actual = y[:, win], y[:, c:]
    S = y.shape[0]
    t_last = np.full(S, COLD_START_DAYS - 1)
    # Local only: default settings, weekday pattern guessed from one week.
    local = forecasting.fit(y_win).forecast(t_last, HOLDOUT)
    # Federated: shared settings and weekday pattern, rotated to this window's weekday alignment.
    shift = (first_weekday + c - COLD_START_DAYS) % 7       # weekday of the window's day 0
    season0 = np.ones((S, 7))
    rate = np.zeros(S)
    for j, code in enumerate(DRUG_CODES):
        d = prior["drugs"].get(code)
        if d is None:
            continue
        prof = np.array(d["weekday"])                         # indexed by calendar weekday
        season0[drug_idx == j] = [prof[(shift + k) % 7] for k in range(7)]
        rate[drug_idx == j] = d["per_100_opd"]
    fed = forecasting.fit(y_win, prior["params"], season0).forecast(t_last, HOLDOUT)
    # Day zero: no demand history at all, only the PHC's OPD. Nothing local is possible.
    opd_recent = np.nanmean(opd[:, win], axis=1)
    idx = (np.arange(c, T) + first_weekday) % 7
    prof_rows = np.array([[season0[s][(k - shift) % 7] for k in range(7)] for s in range(S)])
    zero = (rate * np.nan_to_num(opd_recent) / 100)[:, None] * prof_rows[:, idx]
    return {"local_accuracy": round(1 - _wmape(local, actual), 3),
            "federated_accuracy": round(1 - _wmape(fed, actual), 3),
            "zero_history_accuracy": round(1 - _wmape(zero, actual), 3)}


def evaluate(result: dict) -> dict:
    """Run the federated round on the engine's data and the leave-one-state-out comparison."""
    key = result.get("computed_at")
    if _cache["key"] == key and _cache["value"] is not None:
        return _cache["value"]
    t0 = time.perf_counter()
    arr = result["_arrays"]
    demand, opd_n = arr["demand"], arr["foot"]["opd"]
    N, D, T = demand.shape
    phcs = result["phcs"]
    first_weekday = __import__("datetime").date.fromisoformat(result["days"][0]).weekday()

    per_state = {}
    for sc in sorted({p["state_code"] for p in phcs}):
        rows_ = [i for i, p in enumerate(phcs) if p["state_code"] == sc]
        y = demand[rows_].reshape(-1, T)
        drug_idx = np.tile(np.arange(D), len(rows_))
        opd = np.repeat(opd_n[rows_], D, axis=0)
        per_state[sc] = {"y": y, "drug_idx": drug_idx, "opd": opd, "phcs": len(rows_)}

    updates = {sc: local_update(d["y"], d["drug_idx"], d["opd"], first_weekday) for sc, d in per_state.items()}
    prior = aggregate(updates)
    states = []
    for sc, d in per_state.items():
        others = aggregate({s: u for s, u in updates.items() if s != sc})
        cs = _cold_start(d["y"], d["drug_idx"], d["opd"], others, first_weekday)
        u = updates[sc]
        states.append({"state": sc, "phcs": d["phcs"], "series": u["series"], "params": u["params"],
                       "holdout_accuracy": u["holdout_accuracy"], "default_accuracy": u["default_accuracy"],
                       "raw_rows_kept_local": u["n_obs"],
                       "numbers_shared": 4 + sum(8 for _ in u["drugs"]) + 1, **cs})
    n = len(states)
    avg = lambda k: round(sum(s[k] for s in states) / n, 3) if n else None  # noqa: E731
    value = {
        "method": "FedAvg of per-state Holt-Winters settings, weekday demand patterns and "
                  "demand per 100 OPD; leave-one-state-out cold-start evaluation",
        "cold_start_days": COLD_START_DAYS, "holdout_days": HOLDOUT, "grid_size": len(GRID),
        "prior": prior, "states": states,
        "summary": {"local_accuracy": avg("local_accuracy"), "federated_accuracy": avg("federated_accuracy"),
                    "zero_history_accuracy": avg("zero_history_accuracy"),
                    "numbers_shared_per_state": states[0]["numbers_shared"] if states else 0,
                    "raw_rows_shared": 0},
        "compute_ms": round((time.perf_counter() - t0) * 1000),
    }
    _cache.update(key=key, value=value)
    return value

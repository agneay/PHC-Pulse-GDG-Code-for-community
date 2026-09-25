"""Per-PHC, per-drug demand forecasting.

A damped-trend Holt-Winters model with multiplicative weekly seasonality, run *vectorised*
across every PHC x drug series at once (1,200 series in a few milliseconds). Because the
model is recursive, one pass over history also yields the model state at every past day,
which gives a leakage-free walk-forward backtest for free.

In production this module is the in-process fallback; the same features are exported to
BigQuery and trained with Vertex AI Forecasting / BigQuery ML ARIMA_PLUS (see /vertex and
/bigquery). The interface (`HWResult.forecast`) is what the rest of the engine consumes.
"""
from dataclasses import dataclass

import numpy as np

ALPHA, BETA, GAMMA, PHI = 0.25, 0.04, 0.15, 0.90
PERIOD = 7


@dataclass
class HWResult:
    level: np.ndarray      # (S, T) level after observing day t
    trend: np.ndarray      # (S, T)
    season: np.ndarray     # (S, T, 7) seasonal factors after day t
    yhat: np.ndarray       # (S, T) one-step-ahead prediction made for day t
    resid: np.ndarray      # (S, T) y - yhat (NaN where y missing)

    def forecast(self, t: np.ndarray, horizon: int) -> np.ndarray:
        """Forecast days t+1..t+horizon from the state at per-series index t. -> (S, horizon)"""
        S = self.level.shape[0]
        rows = np.arange(S)
        lvl, tr = self.level[rows, t], self.trend[rows, t]
        seas = self.season[rows, t]                                  # (S, 7)
        h = np.arange(1, horizon + 1)
        damp = np.cumsum(PHI ** h)                                   # sum_{k<=h} phi^k
        base = lvl[:, None] + damp[None, :] * tr[:, None]
        idx = (t[:, None] + h[None, :]) % PERIOD
        return np.clip(base * np.take_along_axis(seas, idx, axis=1), 0, None)

    def sigma(self, t: np.ndarray, window: int = 28) -> np.ndarray:
        """Residual std over the `window` days up to t (per series)."""
        S, T = self.resid.shape
        out = np.empty(S)
        for s in range(S):
            r = self.resid[s, max(0, t[s] - window + 1): t[s] + 1]
            r = r[~np.isnan(r)]
            out[s] = r.std() if r.size > 3 else 1.0
        return out


def fit(y: np.ndarray) -> HWResult:
    """y: (S, T) daily demand, NaN = not reported. Day index t must align with calendar so
    that t % 7 is a fixed weekday across series."""
    S, T = y.shape
    y0 = np.nan_to_num(y[:, :14], nan=np.nanmean(y[:, :14]) if np.isfinite(y[:, :14]).any() else 0)
    lvl = np.maximum(y0.mean(axis=1), 0.05)
    tr = np.zeros(S)
    season = np.ones((S, PERIOD))
    for k in range(PERIOD):
        season[:, k] = np.maximum(y0[:, k::PERIOD].mean(axis=1) / lvl, 0.05)
    season /= season.mean(axis=1, keepdims=True)

    L = np.empty((S, T)); B = np.empty((S, T)); SE = np.empty((S, T, PERIOD))
    YH = np.empty((S, T)); R = np.full((S, T), np.nan)
    for t in range(T):
        k = t % PERIOD
        pred_l = lvl + PHI * tr
        yhat = np.maximum(pred_l * season[:, k], 0)
        yt = y[:, t]
        obs = ~np.isnan(yt)
        yo = np.where(obs, yt, 0.0)
        new_l = ALPHA * (yo / season[:, k]) + (1 - ALPHA) * pred_l
        new_l = np.maximum(new_l, 0.01)
        new_b = BETA * (new_l - lvl) + (1 - BETA) * PHI * tr
        new_s = GAMMA * (yo / new_l) + (1 - GAMMA) * season[:, k]
        lvl = np.where(obs, new_l, pred_l)
        tr = np.where(obs, new_b, PHI * tr)
        season[:, k] = np.where(obs, np.clip(new_s, 0.05, 5), season[:, k])
        L[:, t], B[:, t], SE[:, t] = lvl, tr, season
        YH[:, t] = yhat
        R[obs, t] = yt[obs] - yhat[obs]
    return HWResult(L, B, SE, YH, R)


def days_until_cumulative(forecast: np.ndarray, stock: np.ndarray) -> np.ndarray:
    """First horizon day (1-based) where cumulative forecast demand exceeds stock; inf if never."""
    cum = np.cumsum(forecast, axis=1)
    hit = cum >= stock[:, None]
    first = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, np.inf)
    first = np.where(stock <= 0, 0, first)
    return first


def backtest(y: np.ndarray, stock_close: np.ndarray, hw: HWResult, supply_days: np.ndarray,
             last_t: int, horizon: int = 28, lead: int = 14, window: int = 21) -> dict:
    """Walk-forward evaluation on the last `horizon` days of history.

    * Accuracy: weighted MAPE of the 28-day forecast made at T-28 vs actual demand.
    * Early warning: for every actual stock-out onset in the last 60 days, did the model flag a
      stock-out within `window` days when looking `lead` (=14) days earlier? (recall)
      And of all flags raised in that period, how many were followed by a real stock-out
      (precision)."""
    S, T = y.shape
    cut = np.full(S, last_t - horizon)
    fc = hw.forecast(cut, horizon)
    actual = y[:, last_t - horizon + 1: last_t + 1]
    m = ~np.isnan(actual)
    wmape = float(np.abs(fc - np.nan_to_num(actual))[m].sum() / max(np.nan_to_num(actual)[m].sum(), 1))
    # Weekly totals - the granularity at which indents are actually planned.
    fw = (fc * m).reshape(S, -1, 7).sum(axis=2)
    aw = np.nan_to_num(actual).reshape(S, -1, 7).sum(axis=2)
    wmape_w = float(np.abs(fw - aw).sum() / max(aw.sum(), 1))

    onsets, caught = 0, 0
    flags, flags_true = 0, 0
    stocked_out = stock_close <= 0.5
    for t0 in range(last_t - 60, last_t - lead + 1):
        tv = np.full(S, t0)
        f = hw.forecast(tv, window)
        dts = days_until_cumulative(f, stock_close[:, t0])
        # a warning is only raised if the stock-out lands before the next scheduled delivery
        flagged = (dts <= window) & (dts <= supply_days[:, t0])
        future_out = stocked_out[:, t0 + 1: t0 + window + 1].any(axis=1)
        flags += int(flagged.sum()); flags_true += int((flagged & future_out).sum())
        t_on = t0 + lead
        onset = stocked_out[:, t_on] & ~stocked_out[:, t_on - 1]
        # flagged at t0 -> the warning was live >= `lead` days before the shelf went empty
        onsets += int(onset.sum())
        caught += int((onset & flagged).sum())
    return {
        "wmape_28d": round(wmape, 3),
        "forecast_accuracy": round(max(0.0, 1 - wmape), 3),
        "wmape_weekly": round(wmape_w, 3),
        "weekly_accuracy": round(max(0.0, 1 - wmape_w), 3),
        "stockout_events": onsets,
        "flagged_14d_ahead": caught,
        "recall_14d_ahead": round(caught / onsets, 3) if onsets else None,
        "precision": round(flags_true / flags, 3) if flags else None,
    }

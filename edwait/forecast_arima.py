"""Bounded development-only ARIMA replay, kept outside the production pipeline."""

from datetime import datetime, timezone
import warnings

import numpy as np

from edwait.forecast import CADENCE, HORIZONS

CANDIDATES = {"arima_100": (1, 0, 0), "arima_110": (1, 1, 0)}
SPEC = {"version": "m5-arima-pilot-v1", "orders": CANDIDATES,
        "training_slots": 28 * 96, "minimum_training_slots": 14 * 96,
        "minimum_coverage": .95, "maximum_missing_run": 4,
        "refit_seconds": 86400, "origins_seconds": 3600,
        "max_iterations": 100, "negative_forecasts": "clip to zero",
        "missing_training": "state-space missing observations; no imputation",
        "trend": "constant for ARIMA(1,0,0); none for ARIMA(1,1,0)",
        "stage": "development only", "holdout_scored": False}


def supported(values):
    finite = np.isfinite(values)
    if finite.sum() < SPEC["minimum_training_slots"] or finite.mean() < SPEC["minimum_coverage"]:
        return False
    run = 0
    for present in finite:
        run = 0 if present else run + 1
        if run > SPEC["maximum_missing_run"]:
            return False
    return bool(finite[-1])


def fit_model(values, order):
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ARIMA(values, order=order, trend="c" if order[1] == 0 else "n").fit(method_kwargs={"maxiter": SPEC["max_iterations"]})
    if not fitted.mle_retvals.get("converged", False):
        raise ValueError("nonconvergent_fit")
    return fitted


def replay_facility(slots, start, end, *, fitter=fit_model):
    """Training at each midnight; extend with four newly available slots/hour."""
    output, fits = [], []
    for model, order in CANDIDATES.items():
        day = start
        while day < end:
            training = np.array([slots.get(s, {}).get("wait_minutes", np.nan)
                                 for s in range(day - (SPEC["training_slots"] - 1) * CADENCE, day + 1, CADENCE)], dtype=float)
            state = None
            status = "insufficient_history"
            if supported(training):
                try:
                    state = fitter(training, order)
                    status = "ok"
                except (ValueError, np.linalg.LinAlgError):
                    status = "fit_failed"
            fits.append({"model": model, "day": datetime.fromtimestamp(day, timezone.utc).isoformat(), "status": status})
            for origin in range(day, min(day + 86400, end), 3600):
                if origin > day and state is not None:
                    arrived = np.array([slots.get(s, {}).get("wait_minutes", np.nan)
                                        for s in range(origin - 2700, origin + 1, CADENCE)], dtype=float)
                    try:
                        state = state.extend(arrived)
                    except (ValueError, np.linalg.LinAlgError):
                        state = None
                forecast = None
                # Do not bridge a new long outage after the daily fit.
                recent = [slots.get(s) is not None for s in range(origin - 3 * CADENCE, origin + 1, CADENCE)]
                if not any(recent):
                    state = None
                if state is not None and origin in slots:
                    try:
                        candidate = np.asarray(state.forecast(steps=8), dtype=float)
                        if candidate.shape == (8,) and np.all(np.isfinite(candidate)):
                            forecast = np.maximum(candidate, 0)
                    except (ValueError, np.linalg.LinAlgError):
                        pass
                for horizon in HORIZONS:
                    if origin + horizon * 60 < end:
                        output.append({"model": model, "origin": origin, "horizon_minutes": horizon,
                                       "prediction": float(forecast[horizon // 15 - 1]) if forecast is not None else None})
            day += 86400
    return output, fits

"""Growth kinetics from the batch record's OD600 measurements.

Key idea: in exponential growth, OD = OD0 * e^(mu * t), so ln(OD) vs time is a
straight line whose slope is the specific growth rate mu (1/h).
"""

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import linregress

from .settings import AnalysisSettings



def growth_table(record, settings=None):
    """One row per sample: time from clock, best OD value, pH and pellet data."""
    settings = settings or AnalysisSettings()
    proc = record.process[record.process["used"]]
    od = record.od[record.od["used"]]
    pel = record.pellets[record.pellets["used"]]

    df = proc[["sample", "clock_min", "time_point_min", "ph_probe", "ph_meter"]].merge(
        od[["sample", "a_raw_1", "df_1", "a_corrected_1"]], on="sample"
    ).merge(pel[["sample", "tube_g", "tube_pellet_g", "pellet_g"]], on="sample", how="left")

    # Clock time is the most trustworthy time source (time points disagree between pages).
    df["t_min"] = df["clock_min"] - df["clock_min"].iloc[0]
    df["t_h"] = df["t_min"] / 60

    # Use the dilution-corrected value when the sample was diluted.
    df["od600"] = np.where(df["df_1"] > 1, df["a_corrected_1"], df["a_raw_1"])
    df["od_flag"] = np.where(
        (df["df_1"] == 1) & (df["a_raw_1"] >= settings.od_warning_level) & (df["a_raw_1"] < settings.od_linear_limit),
        "possibly underestimated", "")
    df["ln_od"] = np.log(df["od600"])

    # Recompute pellets from the raw weights; negative values are impossible -> NaN.
    df["pellet_recomputed_g"] = df["tube_pellet_g"] - df["tube_g"]
    df.loc[df["pellet_recomputed_g"] <= 0, "pellet_recomputed_g"] = np.nan
    df["wet_cells_g_per_L"] = df["pellet_recomputed_g"] / (settings.pellet_volume_ml / 1000)
    return df


def interval_rates(df):
    """Specific growth rate between each pair of consecutive samples."""
    rates = pd.DataFrame({
        "from_sample": df["sample"].iloc[:-1].values,
        "to_sample": df["sample"].iloc[1:].values,
        "t_start_h": df["t_h"].iloc[:-1].values,
        "t_end_h": df["t_h"].iloc[1:].values,
        "mu_per_h": np.diff(df["ln_od"]) / np.diff(df["t_h"]),
        "ph_probe_end": df["ph_probe"].iloc[1:].values,
    })
    return rates


def find_mu_max(df, min_points=3, min_r2=0.95):
    """Steepest straight stretch of ln(OD) vs time, using at least `min_points` samples."""
    best = None
    n = len(df)
    for size in range(min_points, n + 1):
        for start in range(0, n - size + 1):
            window = df.iloc[start:start + size]
            fit = linregress(window["t_h"], window["ln_od"])
            r2 = fit.rvalue ** 2
            if r2 >= min_r2 and (best is None or fit.slope > best["mu_max_per_h"]):
                best = {
                    "mu_max_per_h": fit.slope,
                    "r2": r2,
                    "first_sample": int(window["sample"].iloc[0]),
                    "last_sample": int(window["sample"].iloc[-1]),
                    "t_start_h": window["t_h"].iloc[0],
                    "t_end_h": window["t_h"].iloc[-1],
                    "n_points": size,
                }
    if best:
        best["doubling_time_min"] = np.log(2) / best["mu_max_per_h"] * 60
    return best


def logistic(t, k, n0, r):
    """Logistic growth: starts at n0, grows at rate r, levels off at k (carrying capacity)."""
    return k / (1 + ((k - n0) / n0) * np.exp(-r * t))


def fit_logistic(df, exclude_flagged=True):
    data = df[df["od_flag"] == ""] if exclude_flagged else df
    guess = (data["od600"].max() * 1.1, data["od600"].iloc[0], 1.0)
    params, _ = curve_fit(logistic, data["t_h"], data["od600"], p0=guess, maxfev=10000)
    k, n0, r = params
    predicted = logistic(data["t_h"], *params)
    ss_res = ((data["od600"] - predicted) ** 2).sum()
    ss_tot = ((data["od600"] - data["od600"].mean()) ** 2).sum()
    return {"K_od": k, "od0": n0, "r_per_h": r, "r2": 1 - ss_res / ss_tot,
            "n_points": len(data), "excluded_samples": sorted(set(df["sample"]) - set(data["sample"]))}


def label_phases(rates, mu_max):
    """Name each interval by how fast the culture grew compared with mu_max."""
    def phase(mu):
        if mu >= 0.5 * mu_max:
            return "exponential"
        if mu >= 0.1 * mu_max:
            return "deceleration"
        return "stationary"
    rates = rates.copy()
    rates["phase"] = rates["mu_per_h"].apply(phase)
    return rates


def analyze(record, settings=None):
    settings = settings or AnalysisSettings()
    df = growth_table(record, settings)
    if len(df) < 3:
        raise ValueError(f"only {len(df)} usable OD samples; at least 3 are needed for growth kinetics")
    mu = find_mu_max(df) or find_mu_max(df, min_r2=0.90)  # relax if no clean exponential stretch
    if mu is None:
        raise ValueError("no straight exponential stretch in ln(OD600) (R² ≥ 0.90), so μmax can't be estimated")
    rates = label_phases(interval_rates(df), mu["mu_max_per_h"])
    return {"table": df, "mu_max": mu, "rates": rates, "logistic": fit_logistic(df), "settings": settings}

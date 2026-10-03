"""Shared report pieces: run ids, charts, plain-language observations and review questions."""

from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np

from . import style
from .kinetics import logistic

style.apply_theme()

SEVERITIES = ["critical", "major", "minor"]


def run_id(record):
    """e.g. 'group-a_2026-01-15' (group + run date), used for file and folder names."""
    date = record.process.loc[record.process["used"], "raw_date"].iloc[0]
    try:
        date = datetime.strptime(date, "%d/%m/%y").strftime("%Y-%m-%d")
    except ValueError:
        date = date.replace("/", "-")
    group = record.header.get("group_id") or "batch"
    return f"{group}_{date}".lower().replace(" ", "-")


# ---------- charts (all use the shared theme in style.py) ----------

def _new_chart(title, note):
    fig, ax = plt.subplots(figsize=(style.FIGURE_WIDTH, 3.6))
    ax.set_title(title)
    style.subtitle(ax, note)
    return fig, ax


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_od_points(ax, df, column):
    ok, flagged = df[df["od_flag"] == ""], df[df["od_flag"] != ""]
    ax.plot(ok["t_h"], ok[column], "o", color=style.BLUE, label="OD600")
    if len(flagged):
        ax.plot(flagged["t_h"], flagged[column], "o", mfc=style.SURFACE, mec=style.BLUE,
                label="Near instrument limit (excluded from fit)")


def plot_growth(kin, path):
    df, fit = kin["table"], kin["logistic"]
    fig, ax = _new_chart("Growth curve", f"OD600 over time with logistic fit · max OD (K) = {fit['K_od']:.2f}, "
                                         f"R² = {fit['r2']:.3f}")
    t = np.linspace(0, df["t_h"].max(), 200)
    ax.plot(t, logistic(t, fit["K_od"], fit["od0"], fit["r_per_h"]), color=style.INK_MUTED, lw=1.5,
            ls=(0, (4, 3)), label="Logistic fit", zorder=1)
    _plot_od_points(ax, df, "od600")
    ax.set(xlabel="Time (h)", ylabel="OD600")
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right")
    _save(fig, path)


def plot_ln_od(kin, path):
    df, mu = kin["table"], kin["mu_max"]
    fig, ax = _new_chart("Specific growth rate", f"ln(OD600) over time · slope of the steepest linear stretch = μmax "
                                                  f"({mu['mu_max_per_h']:.2f} h⁻¹, R² = {mu['r2']:.3f})")
    _plot_od_points(ax, df, "ln_od")
    window = df[(df["t_h"] >= mu["t_start_h"]) & (df["t_h"] <= mu["t_end_h"])]
    intercept = window["ln_od"].mean() - mu["mu_max_per_h"] * window["t_h"].mean()
    t_line = np.array([mu["t_start_h"], mu["t_end_h"]])
    ax.plot(t_line, intercept + mu["mu_max_per_h"] * t_line, color=style.ORANGE, zorder=1,
            label=f"μmax fit (samples {mu['first_sample']}–{mu['last_sample']})")
    ax.set(xlabel="Time (h)", ylabel="ln(OD600)")
    ax.legend(loc="lower right")
    _save(fig, path)


def plot_ph(kin, path):
    df, mu = kin["table"], kin["mu_max"]
    offset = (df["ph_probe"] - df["ph_meter"]).mean()
    fig, ax = _new_chart("pH during the run", f"Bioreactor probe vs bench meter · probe reads {offset:.2f} higher "
                                               "on average")
    ax.plot(df["t_h"], df["ph_probe"], "o-", color=style.BLUE, label="Bioreactor probe")
    ax.plot(df["t_h"], df["ph_meter"], "o-", color=style.ORANGE, label="Bench pH meter")
    last = df.iloc[-1]
    style.end_label(ax, last["t_h"], last["ph_probe"], "Probe")
    style.end_label(ax, last["t_h"], last["ph_meter"], "Meter")
    ax.axvline(mu["t_end_h"], color=style.BASELINE, lw=1, zorder=0)
    ax.annotate("End of exponential growth", (mu["t_end_h"], df["ph_probe"].max()), xytext=(5, 0),
                textcoords="offset points", fontsize=8, color=style.INK_MUTED, va="top")
    ax.set(xlabel="Time (h)", ylabel="pH")
    ax.set_xlim(right=df["t_h"].max() * 1.1)
    ax.legend(loc="lower left")
    _save(fig, path)


def plot_pellet(kin, path):
    df = kin["table"].dropna(subset=["pellet_recomputed_g"])
    r = np.corrcoef(df["od600"], df["pellet_recomputed_g"])[0, 1]
    fig, ax = _new_chart("Pellet weight vs OD600", f"Wet pellet from 1 mL culture, recomputed from tube weights · "
                                                    f"correlation r = {r:.2f}")
    ax.plot(df["od600"], df["pellet_recomputed_g"] * 1000, "o", color=style.BLUE)
    mg = df["pellet_recomputed_g"] * 1000
    for i, row in df.iterrows():
        # if another point sits just above this one, put this label underneath so they don't collide
        crowded = ((df["od600"] - row["od600"]).abs() < 0.06) & (mg - mg[i]).between(0, 3) & (df.index != i)
        offset = (6, -11) if crowded.any() else (6, 3)
        ax.annotate(f"S{row['sample']}", (row["od600"], mg[i]),
                    textcoords="offset points", xytext=offset, fontsize=8, color=style.INK_MUTED)
    ax.set(xlabel="OD600", ylabel="Wet pellet (mg)")
    ax.set_ylim(bottom=0)
    _save(fig, path)


# ---------- report ----------

def interpretation(findings, kin):
    """Plain-language bullet points about the run, based on the results."""
    df, mu, rates = kin["table"], kin["mu_max"], kin["rates"]
    checks = set(findings["check"])
    lag = "from the start (no visible lag phase)" if rates["phase"].iloc[0] == "exponential" \
        else f"after a lag of about {rates['t_end_h'].iloc[0]:.1f} h"
    bullets = [f"The culture grew exponentially {lag}, at μmax ≈ {mu['mu_max_per_h']:.2f} h⁻¹ "
               f"(doubling every ~{mu['doubling_time_min']:.0f} min)."]

    slowed = rates[(rates["t_start_h"] >= mu["t_end_h"] - 1e-9) & (rates["phase"] != "exponential")]
    if len(slowed):
        s = slowed.iloc[0]
        bullets.append(
            f"Growth first slowed between samples {s['from_sample']} and {s['to_sample']} "
            f"(≈ {s['t_start_h']:.1f}–{s['t_end_h']:.1f} h), when the probe pH was {s['ph_probe_end']:.2f}. "
            f"pH went from {df['ph_probe'].iloc[0]:.1f} to {df['ph_probe'].iloc[-1]:.1f} by the end of the run. "
            "If pH wasn't controlled, acidification may have limited growth. A pH-controlled run would test this.")
    if "od_near_saturation" in checks:
        bullets.append("Samples flagged \"possibly underestimated\" were read near the spectrophotometer's limit "
                       "without dilution. Growth rates for intervals touching them are unreliable, so they were "
                       "excluded from the logistic fit.")
    if "pellet_vs_od" in checks:
        bullets.append("Pellet weights don't follow OD, so they can't be used as a biomass measurement in this run.")
    return "\n".join(f"- {b}" for b in bullets)


def questions_for_review(findings, df):
    """Turn findings into questions to bring to the professor / group."""
    def rows(check):
        return findings[findings["check"] == check]

    questions = []
    for _, f in rows("time_cross_page").iterrows():
        questions.append(f"Sample {f['sample']}: which time is correct, {f['recorded']} or {f['expected']}?")
    for _, f in rows("pellet_negative").iterrows():
        questions.append(f"Sample {f['sample']}: what were the real tube weights? "
                         "The tube + pellet weighs less than the empty tube.")
    if len(rows("od_near_saturation")):
        questions.append("What is our spectrophotometer's linear range? Should we dilute earlier than A = 1.0?")
    if len(rows("ph_offset")):
        questions.append("When were the bioreactor pH probe and the bench pH meter last calibrated, and which do we trust?")
    ph_drop = df["ph_probe"].iloc[0] - df["ph_probe"].min()
    if ph_drop > 0.5:
        questions.append(f"pH fell from {df['ph_probe'].iloc[0]:.1f} to {df['ph_probe'].min():.1f} without control. "
                         "What in the medium caused the acidification, and could it have slowed growth?")
    if len(rows("od_replicate_missing")):
        questions.append("Why was the replicate #2 absorbance not measured?")
    unknown = ", ".join(rows("initials_unknown")["recorded"])
    if unknown:
        questions.append(f"Who do these initials belong to (not on the member list): {unknown}?")
    return "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)) or "None. No open questions."

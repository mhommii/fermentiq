"""The four report charts, drawn in any Theme from style.py.

Each plot function writes a PNG to `out` (a file path or an in-memory buffer).
"""

import io
import logging
import threading

import matplotlib
matplotlib.use("Agg")  # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np

from .kinetics import logistic
from .style import FIGURE_WIDTH, get_theme, rc_params

# Symbols missing from Segoe UI fall back to DejaVu Sans; that fallback is expected, so don't warn about it.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

# matplotlib styling is process-wide; the upload app serves several visitors at once,
# so charts are drawn one at a time to keep each visitor's theme intact.
_DRAW_LOCK = threading.Lock()


def _draw(plot):
    """Run a plot function under the theme's matplotlib settings."""
    def wrapper(kin, out, theme=None):
        t = get_theme(theme)
        with _DRAW_LOCK, plt.rc_context(rc_params(t)):
            fig = plot(kin, t)
            fig.tight_layout()
            fig.savefig(out, format="png")
            plt.close(fig)
    wrapper.__name__ = plot.__name__
    wrapper.__doc__ = plot.__doc__
    return wrapper


def render_png(plot_fn, kin, theme=None):
    """A chart as PNG bytes (nothing written to disk)."""
    buffer = io.BytesIO()
    plot_fn(kin, buffer, theme)
    return buffer.getvalue()


def _new_chart(t, title, note):
    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH, 3.6))
    ax.set_title(title)
    ax.text(0, 1.03, note, transform=ax.transAxes, fontsize=8.5, color=t.ink_secondary, va="bottom")
    return fig, ax


def _end_label(ax, t, x, y, text):
    """Label a line at its last point instead of relying on color alone."""
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8.5, color=t.ink_secondary)


def _plot_od_points(ax, t, df, column):
    ok, flagged = df[df["od_flag"] == ""], df[df["od_flag"] != ""]
    ax.plot(ok["t_h"], ok[column], t.markers[0], color=t.series[0], label="OD600")
    if len(flagged):
        ax.plot(flagged["t_h"], flagged[column], t.markers[0], mfc=t.surface, mec=t.series[0],
                label="Near instrument limit (excluded from fit)")


@_draw
def plot_growth(kin, t):
    """OD600 over time with the logistic fit."""
    df, fit = kin["table"], kin["logistic"]
    fig, ax = _new_chart(t, "Growth curve", f"OD600 over time with logistic fit · max OD (K) = {fit['K_od']:.2f}, "
                                            f"R² = {fit['r2']:.3f}")
    time = np.linspace(0, df["t_h"].max(), 200)
    ax.plot(time, logistic(time, fit["K_od"], fit["od0"], fit["r_per_h"]), color=t.muted, lw=1.5,
            ls=(0, (4, 3)), label="Logistic fit", zorder=1)
    _plot_od_points(ax, t, df, "od600")
    ax.set(xlabel="Time (h)", ylabel="OD600")
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right")
    return fig


@_draw
def plot_ln_od(kin, t):
    """ln(OD600) with the μmax regression window."""
    df, mu = kin["table"], kin["mu_max"]
    fig, ax = _new_chart(t, "Specific growth rate", f"ln(OD600) over time · slope of the steepest linear stretch "
                                                    f"= μmax ({mu['mu_max_per_h']:.2f} h⁻¹, R² = {mu['r2']:.3f})")
    _plot_od_points(ax, t, df, "ln_od")
    window = df[(df["t_h"] >= mu["t_start_h"]) & (df["t_h"] <= mu["t_end_h"])]
    intercept = window["ln_od"].mean() - mu["mu_max_per_h"] * window["t_h"].mean()
    t_line = np.array([mu["t_start_h"], mu["t_end_h"]])
    ax.plot(t_line, intercept + mu["mu_max_per_h"] * t_line, color=t.series[1], ls=t.linestyles[1], zorder=1,
            label=f"μmax fit (samples {mu['first_sample']}–{mu['last_sample']})")
    ax.set(xlabel="Time (h)", ylabel="ln(OD600)")
    ax.legend(loc="lower right")
    return fig


@_draw
def plot_ph(kin, t):
    """Bioreactor probe vs bench meter pH."""
    df, mu = kin["table"], kin["mu_max"]
    offset = (df["ph_probe"] - df["ph_meter"]).mean()
    fig, ax = _new_chart(t, "pH during the run", f"Bioreactor probe vs bench meter · probe reads {offset:.2f} "
                                                 "higher on average")
    ax.plot(df["t_h"], df["ph_probe"], marker=t.markers[0], ls=t.linestyles[0], color=t.series[0],
            label="Bioreactor probe")
    ax.plot(df["t_h"], df["ph_meter"], marker=t.markers[1], ls=t.linestyles[1], color=t.series[1],
            label="Bench pH meter")
    last = df.iloc[-1]
    _end_label(ax, t, last["t_h"], last["ph_probe"], "Probe")
    _end_label(ax, t, last["t_h"], last["ph_meter"], "Meter")
    ax.axvline(mu["t_end_h"], color=t.baseline, lw=1, zorder=0)
    ax.annotate("End of exponential growth", (mu["t_end_h"], df["ph_probe"].max()), xytext=(5, 0),
                textcoords="offset points", fontsize=8, color=t.muted, va="top")
    ax.set(xlabel="Time (h)", ylabel="pH")
    ax.set_xlim(right=df["t_h"].max() * 1.1)
    ax.legend(loc="lower left")
    return fig


@_draw
def plot_pellet(kin, t):
    """Recomputed wet pellet weight against OD600."""
    df = kin["table"].dropna(subset=["pellet_recomputed_g"])
    volume = kin["settings"].pellet_volume_ml
    r = np.corrcoef(df["od600"], df["pellet_recomputed_g"])[0, 1] if len(df) > 2 else float("nan")
    fig, ax = _new_chart(t, "Pellet weight vs OD600", f"Wet pellet from {volume:g} mL culture, recomputed from "
                                                      f"tube weights · correlation r = {r:.2f}")
    mg = df["pellet_recomputed_g"] * 1000
    ax.plot(df["od600"], mg, t.markers[0], color=t.series[0])
    for i, row in df.iterrows():
        # if another point sits just above this one, put this label underneath so they don't collide
        crowded = ((df["od600"] - row["od600"]).abs() < 0.06) & (mg - mg[i]).between(0, 3) & (df.index != i)
        offset = (6, -11) if crowded.any() else (6, 3)
        ax.annotate(f"S{row['sample']}", (row["od600"], mg[i]),
                    textcoords="offset points", xytext=offset, fontsize=8, color=t.muted)
    ax.set(xlabel="OD600", ylabel="Wet pellet (mg)")
    ax.set_ylim(bottom=0)
    return fig


ALL_CHARTS = {  # file name -> plot function, in report order
    "growth_curve": plot_growth,
    "specific_growth_rate": plot_ln_od,
    "ph": plot_ph,
    "pellet_vs_od": plot_pellet,
}

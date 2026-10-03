"""One visual theme for every FermentIQ chart.

All charts must call `apply_theme()` and use the colors below, so every figure
in every report looks like part of the same set. Palette checked for
colorblind safety (blue/orange/aqua, in this fixed order).
"""

import logging

import matplotlib.pyplot as plt

# Surfaces and ink
SURFACE = "#fcfcfb"
INK = "#0b0b0b"          # titles, values
INK_SECONDARY = "#52514e"  # subtitles, legend text
INK_MUTED = "#898781"      # axis labels, ticks, annotations
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

# Data series: always assigned in this order, never cycled
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
BLUE, ORANGE, AQUA = SERIES

FIGURE_WIDTH = 7.5  # inches; every chart uses the same width so they line up in reports


def apply_theme():
    # Symbols missing from Segoe UI fall back to DejaVu Sans; that fallback is expected, so don't warn about it.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"],  # DejaVu covers symbols like μ and ⁻¹
        "font.size": 9.5,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "figure.dpi": 150,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 1,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "axes.labelcolor": INK_MUTED,
        "axes.labelsize": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "semibold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titlepad": 22,
        "axes.prop_cycle": plt.cycler(color=SERIES),
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "lines.linewidth": 2,
        "lines.markersize": 7,
        "lines.markeredgewidth": 1.5,
        "lines.markeredgecolor": SURFACE,  # thin surface ring keeps overlapping markers legible
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "legend.labelcolor": INK_SECONDARY,
    })


def subtitle(ax, text):
    """Grey one-line explanation under the left-aligned title."""
    ax.text(0, 1.03, text, transform=ax.transAxes, fontsize=8.5, color=INK_SECONDARY, va="bottom")


def end_label(ax, x, y, text):
    """Label a line at its last point instead of relying on color alone."""
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8.5, color=INK_SECONDARY)

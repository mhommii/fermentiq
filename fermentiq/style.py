"""Report themes: one set of colors drives the charts, the HTML report and the PDF.

Every chart and report takes a Theme. Series colors were checked for colorblind
safety against each theme's own background (Print is greyscale and relies on
marker shapes and line styles instead of color).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    description: str
    dark: bool
    surface: str          # card / chart background
    page: str             # page background behind cards
    ink: str              # titles, values
    ink_secondary: str    # body text, legend
    muted: str            # axis labels, ticks, notes
    grid: str
    baseline: str
    border: str
    accent: str           # section numbers, links
    series: tuple         # data colors, always used in this order
    status: dict = field(default_factory=dict)  # critical / major / minor (always shown with a text label)
    markers: tuple = ("o", "o", "o")
    linestyles: tuple = ("-", "-", "-")
    table_padding: int = 8  # px; smaller = denser tables


STATUS = {"critical": "#d03b3b", "major": "#ec835a", "minor": "#fab219"}

THEMES = {
    "classic": Theme(
        "classic", "Classic", "Warm off-white with blue and orange. Balanced for screen and print.", False,
        surface="#fcfcfb", page="#f4f3ef", ink="#0b0b0b", ink_secondary="#52514e", muted="#898781",
        grid="#e1e0d9", baseline="#c3c2b7", border="rgba(11,11,11,0.10)", accent="#2a78d6",
        series=("#2a78d6", "#eb6834", "#1baf7a"), status=STATUS),
    "dark": Theme(
        "dark", "Dark", "Dark background for screens and presentations. Not for printing.", True,
        surface="#1a1a19", page="#0d0d0d", ink="#ffffff", ink_secondary="#c3c2b7", muted="#898781",
        grid="#2c2c2a", baseline="#383835", border="rgba(255,255,255,0.10)", accent="#3987e5",
        series=("#3987e5", "#d95926", "#199e70"), status=STATUS),
    "print": Theme(
        "print", "Print (black & white)", "Pure white and greyscale. Lines and markers stay distinct on a "
        "black-and-white printer or photocopy.", False,
        surface="#ffffff", page="#ffffff", ink="#000000", ink_secondary="#333333", muted="#666666",
        grid="#dddddd", baseline="#999999", border="rgba(0,0,0,0.25)", accent="#000000",
        series=("#000000", "#555555", "#888888"),
        status={"critical": "#000000", "major": "#666666", "minor": "#b3b3b3"},
        markers=("o", "s", "^"), linestyles=("-", "--", ":")),
    "lab": Theme(
        "lab", "Lab / clinical", "Crisp white with navy and teal. A formal QA-document look with denser tables.",
        False, surface="#ffffff", page="#eef2f6", ink="#0f1e2e", ink_secondary="#3d4f63", muted="#7a8796",
        grid="#e3e8ee", baseline="#c2ccd6", border="rgba(15,30,46,0.14)", accent="#2d5fa8",
        series=("#2d5fa8", "#e07a2e", "#009aa0"), status=STATUS, table_padding=5),
    "modern": Theme(
        "modern", "Modern tech", "Charcoal-blue with mint and electric-blue accents. A data-science dashboard look.",
        True, surface="#111827", page="#0b1120", ink="#e6edf5", ink_secondary="#a9b6c6", muted="#6b7a8f",
        grid="#1f2a3a", baseline="#2c3a4f", border="rgba(62,230,176,0.18)", accent="#10a882",
        series=("#10a882", "#3b8ef0", "#d6578f"), status=STATUS),
}
DEFAULT_THEME = "classic"

FIGURE_WIDTH = 7.5  # inches; every chart uses the same width so they line up in reports


def get_theme(theme):
    """Accept a Theme or a theme key ('classic', 'dark', ...)."""
    if isinstance(theme, Theme):
        return theme
    return THEMES[theme or DEFAULT_THEME]


def rc_params(theme):
    """Matplotlib settings for a theme (applied per chart, never globally)."""
    t = get_theme(theme)
    return {
        "font.family": ["Segoe UI", "DejaVu Sans"],  # DejaVu covers symbols like μ and ⁻¹
        "font.size": 9.5,
        "figure.facecolor": t.surface,
        "savefig.facecolor": t.surface,
        "figure.dpi": 150,
        "axes.facecolor": t.surface,
        "axes.edgecolor": t.baseline,
        "axes.linewidth": 1,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "axes.labelcolor": t.muted,
        "axes.labelsize": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "semibold",
        "axes.titlecolor": t.ink,
        "axes.titlelocation": "left",
        "axes.titlepad": 22,
        "grid.color": t.grid,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": t.muted,
        "ytick.color": t.muted,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "lines.linewidth": 2,
        "lines.markersize": 7,
        "lines.markeredgewidth": 1.5,
        "lines.markeredgecolor": t.surface,  # thin surface ring keeps overlapping markers legible
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "legend.labelcolor": t.ink_secondary,
        "text.color": t.ink_secondary,
    }

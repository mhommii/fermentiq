"""The batch report as one self-contained HTML page (charts embedded), in any Theme.

Open it in any browser; Ctrl+P -> Save as PDF gives a printable copy in the same theme.
"""

import base64
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from . import about
from .charts import plot_growth, plot_ln_od, plot_pellet, plot_ph, render_png
from .report import interpretation, questions_for_review, run_id
from .style import get_theme

ISSUE_NAMES = {
    "pellet_calc": "Pellet weight calculation",
    "pellet_negative": "Impossible pellet weight",
    "copied_value": "Possible copied value",
    "od_not_diluted": "OD not diluted",
    "od_near_saturation": "OD near instrument limit",
    "od_corrected_calc": "Corrected OD calculation",
    "od_corrected_missing": "Corrected OD missing",
    "od_corrected_na": "Corrected OD recorded as N/A",
    "od_replicate_missing": "OD replicate not measured",
    "time_vs_clock": "Time point vs clock time",
    "time_cross_page": "Time point differs between pages",
    "time_units": "Time point without units",
    "ph_offset": "pH probe vs meter offset",
    "temp_deviation": "Temperature out of range",
    "setpoint_change": "Setpoint changed",
    "pellet_vs_od": "Pellet weight doesn't track OD",
    "gram_inconsistent": "Gram stain inconsistent with organism",
    "gram_selection_missing": "Gram stain Y/N not selected",
    "highlight_selection": "Choice marked by highlighting",
    "initials_missing": "Missing initials",
    "self_verified": "Operator verified own entry",
    "initials_unknown": "Initials not on member list",
    "serial_blank": "Equipment serial number blank",
    "unused_rows": "Unused rows not struck through",
    "date_format": "Date format",
    "units_in_value": "Units inside numeric cells",
    "inconsistent_terms": "Inconsistent terminology",
    "blank_cells": "Blank cells (should be N/A)",
}

SEVERITY_LABELS = {"critical": "Critical", "major": "Major", "minor": "Minor"}


def run_title(record, kin):
    """'E. coli growth in BioFlo 120 BIOREACTOR · Group A · 02 Oct 2026' style subtitle parts."""
    run_date = record.process.loc[record.process["used"], "raw_date"].iloc[0]
    try:
        run_date = datetime.strptime(run_date, "%d/%m/%y").strftime("%d %b %Y")
    except ValueError:
        pass
    organism = kin["settings"].organism_for(record)
    return organism, record.header.get("equipment", ""), record.header.get("group_id", ""), run_date


def sample_label(sample):
    sample = str(sample)
    if sample in ("all", "-"):
        return "Run" if sample == "all" else "Record"
    return ", ".join(f"S{s.strip()}" for s in sample.split(","))


def _css(t):
    return f"""
:root {{
  --surface: {t.surface}; --page: {t.page}; --ink: {t.ink}; --ink-2: {t.ink_secondary};
  --muted: {t.muted}; --line: {t.grid}; --border: {t.border}; --accent: {t.accent}; --pad: {t.table_padding}px;
  color-scheme: {"dark" if t.dark else "light"};
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif; }}
main {{ max-width: 980px; margin: 32px auto; padding: 0 16px; }}
section, header {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 24px 28px; margin-bottom: 16px; }}
h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 4px; }}
h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 16px; }}
h2 .num {{ color: var(--accent); font-weight: 600; margin-right: 8px; }}
h3 {{ font-size: 13px; font-weight: 600; margin: 20px 0 8px; display: flex; align-items: center; gap: 8px; }}
a {{ color: var(--accent); }}
.meta {{ color: var(--ink-2); margin: 0; }}
.meta-small {{ color: var(--muted); font-size: 12px; margin-top: 8px; display: flex;
  justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
.card {{ border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
.card .label {{ color: var(--ink-2); font-size: 12px; }}
.card .value {{ font-size: 24px; font-weight: 600; margin: 2px 0; }}
.card .sub {{ color: var(--muted); font-size: 12px; }}
.counts {{ list-style: none; padding: 0; margin: 6px 0 0; }}
.counts li {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
.counts b {{ min-width: 18px; }}
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none;
  box-shadow: 0 0 0 1px var(--border); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; font-weight: 600; color: var(--ink-2); font-size: 12px;
  border-bottom: 1px solid var(--line); padding: 6px 10px 6px 0; }}
td {{ border-bottom: 1px solid var(--line); padding: var(--pad) 10px var(--pad) 0; vertical-align: top; }}
tr:last-child td {{ border-bottom: none; }}
td.sample {{ white-space: nowrap; font-weight: 600; width: 70px; }}
td.issue {{ width: 190px; }}
td.values {{ width: 230px; font-variant-numeric: tabular-nums; }}
.arrow {{ color: var(--muted); margin: 0 4px; }}
.expected {{ color: var(--ink-2); }}
td.why {{ color: var(--ink-2); }}
.num-table td, .num-table th {{ font-variant-numeric: tabular-nums; }}
.num-table td.r, .num-table th.r {{ text-align: right; padding-right: 18px; }}
.flag {{ color: var(--muted); font-size: 12px; }}
details summary {{ cursor: pointer; list-style: none; }}
details summary::-webkit-details-marker {{ display: none; }}
details summary h3::after {{ content: "Show"; font-weight: 400; color: var(--muted); font-size: 12px; margin-left: 6px; }}
details[open] summary h3::after {{ content: "Hide"; }}
figure {{ margin: 16px 0; }}
figure img {{ width: 100%; height: auto; display: block; border-radius: 6px; }}
ul.obs, ol.questions {{ margin: 0; padding-left: 20px; }}
ul.obs li, ol.questions li {{ margin-bottom: 6px; }}
.note {{ color: var(--muted); font-size: 12px; margin: 0 0 12px; }}
footer {{ color: var(--muted); font-size: 12px; text-align: center; margin: 8px 0 32px; }}
@media (max-width: 720px) {{
  .cards {{ grid-template-columns: 1fr 1fr; }}
  td.issue, td.values {{ width: auto; }}
}}
@media print {{
  @page {{ size: A4; margin: 14mm; }}
  * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}  /* keep the chosen theme on paper */
  body {{ font-size: 11px; }}
  main {{ margin: 0; max-width: none; padding: 0; }}
  section, header {{ margin-bottom: 10px; }}
  table, figure, .card, h3 {{ break-inside: avoid; }}
  details summary h3::after {{ content: ""; }}
}}
"""


def _chart(plot_fn, kin, alt, theme):
    data = base64.b64encode(render_png(plot_fn, kin, theme)).decode()
    return f'<figure><img src="data:image/png;base64,{data}" alt="{escape(alt)}"></figure>'


def _findings_table(rows):
    body = "".join(
        f"<tr><td class='sample'>{escape(sample_label(r['sample']))}</td>"
        f"<td class='issue'>{escape(ISSUE_NAMES.get(r['check'], r['check']))}</td>"
        f"<td class='values'><span class='recorded'>{escape(str(r['recorded']))}</span>"
        f"<span class='arrow'>→</span><span class='expected'>{escape(str(r['expected']))}</span></td>"
        f"<td class='why'>{escape(str(r['message']))}</td></tr>"
        for _, r in rows.iterrows())
    return ("<table><thead><tr><th>Sample</th><th>Issue</th><th>Recorded → Expected</th>"
            f"<th>Why it matters</th></tr></thead><tbody>{body}</tbody></table>")


def _findings_section(findings, t):
    parts = []
    for key, label in SEVERITY_LABELS.items():
        rows = findings[findings["severity"] == key]
        if not len(rows):
            continue
        heading = f"<h3><span class='dot' style='background:{t.status[key]}'></span>{label} ({len(rows)})</h3>"
        if key == "minor":
            parts.append(f"<details class='minor'><summary>{heading}</summary>{_findings_table(rows)}</details>")
        else:
            parts.append(heading + _findings_table(rows))
    return "".join(parts) or "<p class='meta'>No issues found.</p>"


def _sample_table(df):
    def pellet_mg(value):
        return "–" if pd.isna(value) else f"{value * 1000:.1f}"

    rows = "".join(
        f"<tr><td>S{r['sample']}</td><td class='r'>{r['t_min']:.0f}</td><td class='r'>{r['od600']:.3f}</td>"
        f"<td class='r'>{r['ph_probe']:.2f}</td><td class='r'>{r['ph_meter']:.2f}</td>"
        f"<td class='r'>{pellet_mg(r['pellet_recomputed_g'])}</td>"
        f"<td class='flag'>{escape(r['od_flag'].capitalize())}</td></tr>"
        for _, r in df.iterrows())
    return ("<table class='num-table'><thead><tr><th>Sample</th><th class='r'>Time (min)</th>"
            "<th class='r'>OD600</th><th class='r'>pH probe</th><th class='r'>pH meter</th>"
            f"<th class='r'>Wet pellet (mg)</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table>")


def _list_items(markdown_lines, tag):
    items = []
    for line in markdown_lines.splitlines():
        text = line.lstrip("-0123456789. ").strip()
        if text:
            items.append(f"<li>{escape(text)}</li>")
    cls = "obs" if tag == "ul" else "questions"
    return f"<{tag} class='{cls}'>{''.join(items)}</{tag}>"


def write_html_report(record, findings, kin, out_dir="data/private", rid=None, theme=None):
    rid = rid or run_id(record)
    report_dir = Path(out_dir) / "reports" / rid
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "report.html"
    path.write_text(build_html_report(record, findings, kin, theme), encoding="utf-8")
    return path


def build_html_report(record, findings, kin, theme=None):
    """The full report page as a string. Nothing is written to disk (used by the upload app)."""
    t = get_theme(theme)
    df, mu, fit = kin["table"], kin["mu_max"], kin["logistic"]
    organism, equipment, group, run_date = run_title(record, kin)
    counts = findings["severity"].value_counts()
    count_items = "".join(
        f"<li><span class='dot' style='background:{t.status[key]}'></span><b>{counts.get(key, 0)}</b>{label}</li>"
        for key, label in SEVERITY_LABELS.items())
    excluded = ", ".join(f"S{s}" for s in fit["excluded_samples"])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FermentIQ Batch Review</title>
<style>{_css(t)}</style>
</head>
<body>
<main>
<header>
  <h1>FermentIQ · Batch Record Review</h1>
  <p class="meta">{escape(organism)} growth in {escape(equipment)}
    · {escape(group)} · {escape(run_date)} · {len(df)} samples · {df['t_min'].max():.0f} min run</p>
  <div class="meta-small"><span>Source: {escape(Path(record.source).name)}</span>
    <span>Generated {datetime.now():%d %b %Y, %H:%M} · {escape(t.label)} theme</span></div>
</header>

<section>
  <div class="cards">
    <div class="card"><div class="label">Maximum specific growth rate</div>
      <div class="value">{mu['mu_max_per_h']:.2f} h⁻¹</div>
      <div class="sub">S{mu['first_sample']}–S{mu['last_sample']} · R² {mu['r2']:.3f}</div></div>
    <div class="card"><div class="label">Doubling time</div>
      <div class="value">{mu['doubling_time_min']:.0f} min</div>
      <div class="sub">ln 2 / μmax</div></div>
    <div class="card"><div class="label">Maximum OD600</div>
      <div class="value">{fit['K_od']:.2f}</div>
      <div class="sub">Logistic fit · R² {fit['r2']:.3f}</div></div>
    <div class="card"><div class="label">Findings</div><ul class="counts">{count_items}</ul></div>
  </div>
</section>

<section>
  <h2><span class="num">1</span>Data integrity findings</h2>
  <p class="note">Every calculation and entry in the batch record was re-checked. Recorded values are shown
    next to what they should be.</p>
  {_findings_section(findings, t)}
</section>

<section>
  <h2><span class="num">2</span>Growth kinetics</h2>
  <p class="note">Time from clock time. OD600 uses the dilution-corrected value where a sample was diluted.
    {('Excluded from fit: ' + excluded + ' (read near instrument limit).') if excluded else ''}</p>
  {_chart(plot_growth, kin, "Growth curve", t)}
  {_chart(plot_ln_od, kin, "Specific growth rate", t)}
  <h3>Key observations</h3>
  {_list_items(interpretation(findings, kin), "ul")}
  <h3>Sample data</h3>
  {_sample_table(df)}
</section>

<section>
  <h2><span class="num">3</span>Process and instruments</h2>
  {_chart(plot_ph, kin, "pH during the run", t)}
  {_chart(plot_pellet, kin, "Pellet weight vs OD600", t)}
</section>

<section>
  <h2><span class="num">4</span>Questions for review</h2>
  {_list_items(questions_for_review(findings, df), "ol")}
</section>

<footer>{about.NAME} · {escape(about.TAGLINE.lower())}<br>
  Built by {escape(about.AUTHOR)} · <a href="{about.GITHUB_URL}">GitHub</a> ·
  <a href="{about.LINKEDIN_URL}">LinkedIn</a></footer>
</main>
<script>
  // expand collapsed sections when printing so nothing is hidden on paper
  window.addEventListener("beforeprint", () => document.querySelectorAll("details").forEach(d => d.open = true));
</script>
</body>
</html>
"""

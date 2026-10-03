"""Write the batch report as one self-contained HTML page (charts embedded).

Open it in any browser; Ctrl+P -> Save as PDF gives a clean printable copy.
"""

import base64
import io
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from . import style
from .report import (interpretation, plot_growth, plot_ln_od, plot_pellet, plot_ph,
                     questions_for_review, run_id)

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

SEVERITY = {  # label, status color (always shown with the text label, never alone)
    "critical": ("Critical", "#d03b3b"),
    "major": ("Major", "#ec835a"),
    "minor": ("Minor", "#fab219"),
}

CSS = f"""
:root {{
  --surface: {style.SURFACE}; --page: #f4f3ef; --ink: {style.INK}; --ink-2: {style.INK_SECONDARY};
  --muted: {style.INK_MUTED}; --line: {style.GRID}; --border: rgba(11,11,11,0.10);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif; }}
main {{ max-width: 980px; margin: 32px auto; padding: 0 16px; }}
section, header {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 24px 28px; margin-bottom: 16px; }}
h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 4px; }}
h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 16px; }}
h2 .num {{ color: var(--muted); font-weight: 400; margin-right: 8px; }}
h3 {{ font-size: 13px; font-weight: 600; margin: 20px 0 8px; display: flex; align-items: center; gap: 8px; }}
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
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; font-weight: 600; color: var(--ink-2); font-size: 12px;
  border-bottom: 1px solid var(--line); padding: 6px 10px 6px 0; }}
td {{ border-bottom: 1px solid var(--line); padding: 8px 10px 8px 0; vertical-align: top; }}
tr:last-child td {{ border-bottom: none; }}
td.sample {{ white-space: nowrap; font-weight: 600; width: 70px; }}
td.issue {{ width: 190px; }}
td.values {{ width: 230px; font-variant-numeric: tabular-nums; }}
.recorded {{ color: var(--ink); }}
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
  body {{ background: #fff; font-size: 11px; }}
  main {{ margin: 0; max-width: none; padding: 0; }}
  section, header {{ border: none; padding: 0 0 12px; margin-bottom: 12px; border-radius: 0; }}
  table, figure, .card, h3 {{ break-inside: avoid; }}
  details summary h3::after {{ content: ""; }}
}}
"""


def _chart(plot_fn, kin, alt):
    buffer = io.BytesIO()
    plot_fn(kin, buffer)
    data = base64.b64encode(buffer.getvalue()).decode()
    return f'<figure><img src="data:image/png;base64,{data}" alt="{escape(alt)}"></figure>'


def _findings_table(rows):
    body = "".join(
        f"<tr><td class='sample'>{escape(_sample_label(r['sample']))}</td>"
        f"<td class='issue'>{escape(ISSUE_NAMES.get(r['check'], r['check']))}</td>"
        f"<td class='values'><span class='recorded'>{escape(str(r['recorded']))}</span>"
        f"<span class='arrow'>→</span><span class='expected'>{escape(str(r['expected']))}</span></td>"
        f"<td class='why'>{escape(str(r['message']))}</td></tr>"
        for _, r in rows.iterrows())
    return ("<table><thead><tr><th>Sample</th><th>Issue</th><th>Recorded → Expected</th>"
            f"<th>Why it matters</th></tr></thead><tbody>{body}</tbody></table>")


def _sample_label(sample):
    sample = str(sample)
    if sample in ("all", "-"):
        return "Run" if sample == "all" else "Record"
    return ", ".join(f"S{s.strip()}" for s in sample.split(","))


def _findings_section(findings):
    parts = []
    for key, (label, color) in SEVERITY.items():
        rows = findings[findings["severity"] == key]
        if not len(rows):
            continue
        heading = f"<h3><span class='dot' style='background:{color}'></span>{label} ({len(rows)})</h3>"
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


def write_html_report(record, findings, kin, out_dir="data/private", rid=None):
    rid = rid or run_id(record)
    report_dir = Path(out_dir) / "reports" / rid
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "report.html"
    path.write_text(build_html_report(record, findings, kin), encoding="utf-8")
    return path


def build_html_report(record, findings, kin):
    """The full report page as a string. Nothing is written to disk (used by the upload app)."""
    df, mu, fit = kin["table"], kin["mu_max"], kin["logistic"]
    header = record.header
    run_date = record.process.loc[record.process["used"], "raw_date"].iloc[0]
    try:
        run_date = datetime.strptime(run_date, "%d/%m/%y").strftime("%d %b %Y")
    except ValueError:
        pass
    counts = findings["severity"].value_counts()
    count_items = "".join(
        f"<li><span class='dot' style='background:{color}'></span><b>{counts.get(key, 0)}</b>{label}</li>"
        for key, (label, color) in SEVERITY.items())
    excluded = ", ".join(f"S{s}" for s in fit["excluded_samples"])

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FermentIQ Batch Review</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
  <h1>FermentIQ · Batch Record Review</h1>
  <p class="meta">{escape(header.get('organism', ''))} growth in {escape(header.get('equipment', ''))}
    · {escape(header.get('group_id', ''))} · {escape(run_date)} · {len(df)} samples · {df['t_min'].max():.0f} min run</p>
  <div class="meta-small"><span>Source: {escape(Path(record.source).name)}</span>
    <span>Generated {datetime.now():%d %b %Y, %H:%M}</span></div>
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
  {_findings_section(findings)}
</section>

<section>
  <h2><span class="num">2</span>Growth kinetics</h2>
  <p class="note">Time from clock time. OD600 uses the dilution-corrected value where a sample was diluted.
    {('Excluded from fit: ' + excluded + ' (read near instrument limit).') if excluded else ''}</p>
  {_chart(plot_growth, kin, "Growth curve")}
  {_chart(plot_ln_od, kin, "Specific growth rate")}
  <h3>Key observations</h3>
  {_list_items(interpretation(findings, kin), "ul")}
  <h3>Sample data</h3>
  {_sample_table(df)}
</section>

<section>
  <h2><span class="num">3</span>Process and instruments</h2>
  {_chart(plot_ph, kin, "pH during the run")}
  {_chart(plot_pellet, kin, "Pellet weight vs OD600")}
</section>

<section>
  <h2><span class="num">4</span>Questions for review</h2>
  {_list_items(questions_for_review(findings, df), "ol")}
</section>

<footer>FermentIQ · automated batch record review and growth analysis</footer>
</main>
<script>
  // expand collapsed sections when printing so nothing is hidden on paper
  window.addEventListener("beforeprint", () => document.querySelectorAll("details").forEach(d => d.open = true));
</script>
</body>
</html>
"""
    return html

"""FermentIQ upload app: upload a batch record, review it, pick a theme, download the report.

Run locally:  streamlit run app.py   (or double-click "Start FermentIQ App.bat")

Privacy: uploads are analyzed in memory for this browser session only. Nothing from the
file is saved to disk or shared between visitors; only an anonymous count is kept (fermentiq/usage.py).
"""

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from fermentiq import about, usage
from fermentiq.charts import ALL_CHARTS, render_png
from fermentiq.checks import run_checks
from fermentiq.exports import build_chart_zip, build_excel, build_pdf
from fermentiq.html_report import ISSUE_NAMES, SEVERITY_LABELS, build_html_report, run_title, sample_label
from fermentiq.kinetics import analyze
from fermentiq.parse_record import parse_record
from fermentiq.report import interpretation, questions_for_review, run_id
from fermentiq.settings import GRAM_TYPES, AnalysisSettings
from fermentiq.style import DEFAULT_THEME, THEMES

# anonymized public demo record (FERMENTIQ_SAMPLE_PDF lets tests point elsewhere)
SAMPLE_PDF = Path(os.environ.get("FERMENTIQ_SAMPLE_PDF",
                                 Path(__file__).parent / "samples" / "sample_batch_record.pdf"))
REPORT_HEIGHT = 1600  # px; the embedded full report scrolls inside this frame
DEFAULTS = AnalysisSettings()

st.set_page_config(page_title="FermentIQ", page_icon=":material/science:", layout="wide")
state = st.session_state
state.setdefault("analyses", {})  # (file key, settings) -> analysis, for this browser session only
state.setdefault("counted", set())  # file keys already added to the anonymous counter


# ---------- analysis (in memory) ----------

def analyse(key, name, data, settings):
    cache_key = (key, settings)
    if cache_key not in state.analyses:
        try:
            record = parse_record(io.BytesIO(data), source_name=name)
            findings = run_checks(record, settings)
            kin = analyze(record, settings)
            state.analyses[cache_key] = {"record": record, "findings": findings, "kin": kin}
            ok = True
        except ValueError as error:  # FermentIQ's own plain-language messages
            state.analyses[cache_key] = {"error": f"Reason: {error}."}
            ok = False
        except Exception:  # damaged file, scan, or not a PDF: no technical traceback for visitors
            state.analyses[cache_key] = {"error": "The file couldn't be read. Make sure it's the typed batch "
                                                  "record PDF, not a scan or photo."}
            ok = False
        if key not in state.counted and key != "sample":  # count each uploaded file once, never the demo
            state.counted.add(key)
            usage.record(success=ok)
    return state.analyses[cache_key]


# ---------- sidebar ----------

with st.sidebar:
    st.title("FermentIQ")
    st.caption(about.TAGLINE)

    uploads = st.file_uploader("Batch record PDF", type="pdf", accept_multiple_files=True,
                               help="Typed BioFlo 120 batch record. You can upload several; each gets its own report.")
    sources = [(f.file_id, f.name, f.getvalue()) for f in uploads]
    if sources:
        state.use_sample = False
    elif state.get("use_sample") and SAMPLE_PDF.exists():
        sources = [("sample", "Sample batch record (anonymized)", SAMPLE_PDF.read_bytes())]

    # forget analyses of files the visitor removed
    live = {key for key, _, _ in sources}
    for cache_key in [k for k in state.analyses if k[0] not in live]:
        del state.analyses[cache_key]

    current = sources[0] if sources else None
    if len(sources) > 1:
        names = [name for _, name, _ in sources]
        current = sources[names.index(st.selectbox("Report for", names))]

    st.divider()
    theme_key = st.radio("Report theme", list(THEMES), index=list(THEMES).index(DEFAULT_THEME),
                         format_func=lambda k: THEMES[k].label, captions=[t.description for t in THEMES.values()])

    with st.expander("Advanced settings"):
        st.caption("Defaults match the BioFlo 120 E. coli batch record. Change them only if your experiment differs.")
        organism = st.text_input("Organism", placeholder="As written on the batch record")
        gram_type = st.selectbox("Gram type", GRAM_TYPES, format_func=str.capitalize,
                                 help="Used to check the Gram stain observations.")
        pellet_volume = st.number_input("Pellet culture volume (mL)", 0.1, 50.0, DEFAULTS.pellet_volume_ml, 0.1)
        col1, col2 = st.columns(2)
        temp_setpoint = col1.number_input("Temp. setpoint (°C)", 0.0, 100.0, DEFAULTS.temp_setpoint_c, 0.5)
        temp_tolerance = col2.number_input("± tolerance (°C)", 0.1, 10.0, DEFAULTS.temp_tolerance_c, 0.1)
        col1, col2 = st.columns(2)
        od_limit = col1.number_input("OD dilution limit", 0.2, 3.0, DEFAULTS.od_linear_limit, 0.05,
                                     help="Readings at or above this must be diluted.")
        od_warning = col2.number_input("OD warning level", 0.1, 3.0, DEFAULTS.od_warning_level, 0.05,
                                       help="Undiluted readings between this and the limit are flagged.")
        ph_tolerance = st.number_input("pH probe vs meter tolerance", 0.01, 1.0, DEFAULTS.ph_offset_tolerance, 0.01)
        if od_warning >= od_limit:
            st.warning("The OD warning level must be below the dilution limit; using the defaults.")
            od_limit, od_warning = DEFAULTS.od_linear_limit, DEFAULTS.od_warning_level
    settings = AnalysisSettings(organism=organism, gram_type=gram_type, pellet_volume_ml=pellet_volume,
                                temp_setpoint_c=temp_setpoint, temp_tolerance_c=temp_tolerance,
                                od_linear_limit=od_limit, od_warning_level=od_warning,
                                ph_offset_tolerance=ph_tolerance)

    result = analyse(*current, settings) if current else None
    if result and "error" not in result:
        st.divider()
        st.subheader("Download")
        record, findings, kin = result["record"], result["findings"], result["kin"]
        name = run_id(record)
        st.download_button("Report (HTML)", lambda: build_html_report(record, findings, kin, theme_key),
                           file_name=f"{name}_report.html", mime="text/html", icon=":material/language:",
                           width="stretch")
        st.download_button("Report (PDF)", lambda: build_pdf(record, findings, kin, theme_key),
                           file_name=f"{name}_report.pdf", mime="application/pdf",
                           icon=":material/picture_as_pdf:", width="stretch")
        st.download_button("Data (Excel)", lambda: build_excel(record, findings, kin),
                           file_name=f"{name}_data.xlsx", icon=":material/table_view:", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("Charts (PNG, zip)", lambda: build_chart_zip(kin, theme_key),
                           file_name=f"{name}_charts.zip", mime="application/zip", icon=":material/image:",
                           width="stretch")

    st.divider()
    st.caption(":material/lock: Files are analyzed in memory and never stored. "
               f"{usage.records_checked()} batch records checked since the app last started.")
    st.markdown(f"Built by **{about.AUTHOR}**  \n[GitHub]({about.GITHUB_URL}) · [LinkedIn]({about.LINKEDIN_URL})")


# ---------- main area ----------

def welcome():
    st.title("FermentIQ")
    st.markdown(f"#### {about.TAGLINE}")
    st.markdown("Upload a BioFlo 120 batch record and get an automated QA-style review in seconds: every "
                "calculation re-checked, documentation gaps flagged, and the growth kinetics worked out.")

    st.subheader("How to use it")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**1. Upload**  \nDrop one or more typed batch-record PDFs into the sidebar.")
    c2.markdown("**2. Review**  \nCheck the summary, findings and growth charts in the tabs.")
    c3.markdown("**3. Download**  \nPick a theme and download the report as PDF or HTML, the data as "
                "Excel, or the charts as images.")
    if SAMPLE_PDF.exists():
        if st.button("Try the sample record", icon=":material/play_arrow:", type="primary"):
            state.use_sample = True
            st.rerun()

    st.subheader("What it checks")
    c1, c2 = st.columns(2)
    c1.markdown("**Data integrity**\n- Pellet weights and dilution-corrected absorbance recalculated\n"
                "- Time points vs clock times, and across pages\n- OD readings near the instrument limit\n"
                "- pH probe vs bench meter agreement, temperature and setpoint changes\n"
                "- Gram stain results vs the organism")
    c2.markdown("**Good Documentation Practice**\n- Missing or unknown initials, self-verification\n"
                "- Blank required fields, unused rows not struck through\n"
                "- Inconsistent dates, units and terminology\n\n**Growth kinetics**\n"
                "- μmax, doubling time, logistic fit, growth phases")

    st.subheader("Supported form and privacy")
    st.markdown("FermentIQ reads the typed **BioFlo 120 E. coli batch record** form (process table, pellet and "
                "Gram stain table, OD600 table). Scans, photos and other forms are rejected with a clear message.\n\n"
                "Your file is analyzed in memory on the app's server for your session only. It is never saved, "
                "logged or shown to anyone else. The only thing kept is an anonymous count of records checked.")

    st.subheader("About")
    st.markdown(f"FermentIQ is a biomanufacturing portfolio project by **{about.AUTHOR}**, built to turn paper-style "
                f"batch records into reviewed, analyzable data. [GitHub]({about.GITHUB_URL}) · "
                f"[LinkedIn]({about.LINKEDIN_URL})")


def show_report(name, result):
    record, findings, kin = result["record"], result["findings"], result["kin"]
    df, mu, fit = kin["table"], kin["mu_max"], kin["logistic"]
    organism, equipment, group, run_date = run_title(record, kin)
    st.title("Batch Record Review")
    st.caption(f"{organism} growth in {equipment} · {group} · {run_date} · {len(df)} samples · "
               f"{df['t_min'].max():.0f} min run · {name}")

    summary, findings_tab, kinetics_tab, process_tab, full_tab = st.tabs(
        ["Summary", "Findings", "Growth kinetics", "Process & instruments", "Full report"])

    with summary:
        counts = findings["severity"].value_counts()
        c = st.columns(4)
        c[0].metric("Max specific growth rate", f"{mu['mu_max_per_h']:.2f} h⁻¹", border=True,
                    help=f"Samples {mu['first_sample']}–{mu['last_sample']}, R² {mu['r2']:.3f}")
        c[1].metric("Doubling time", f"{mu['doubling_time_min']:.0f} min", border=True, help="ln 2 / μmax")
        c[2].metric("Maximum OD600", f"{fit['K_od']:.2f}", border=True, help=f"Logistic fit, R² {fit['r2']:.3f}")
        c[3].metric("Findings", " / ".join(str(counts.get(k, 0)) for k in SEVERITY_LABELS), border=True,
                    help="Critical / major / minor")
        left, right = st.columns(2)
        with left:
            st.subheader("Key observations")
            st.markdown(interpretation(findings, kin))
        with right:
            st.subheader("Questions for review")
            st.markdown(questions_for_review(findings, df))

    with findings_tab:
        chosen = st.pills("Severity", list(SEVERITY_LABELS), selection_mode="multi",
                          default=["critical", "major"], format_func=lambda k: SEVERITY_LABELS[k])
        shown = findings[findings["severity"].isin(chosen or [])]
        table = pd.DataFrame({
            "Severity": shown["severity"].astype(str).str.capitalize(),
            "Sample": shown["sample"].map(sample_label),
            "Issue": shown["check"].map(lambda c: ISSUE_NAMES.get(c, c)),
            "Recorded": shown["recorded"].astype(str), "Expected": shown["expected"].astype(str),
            "Why it matters": shown["message"],
        })
        st.caption(f"{len(shown)} of {len(findings)} findings shown")
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Why it matters": st.column_config.TextColumn(width="large")})

    with kinetics_tab:
        for chart in ("growth_curve", "specific_growth_rate"):
            st.image(render_png(ALL_CHARTS[chart], kin, theme_key), width="stretch")
        st.subheader("Sample data")
        st.dataframe(pd.DataFrame({
            "Sample": df["sample"].map(lambda s: f"S{s}"), "Time (min)": df["t_min"].round(0),
            "OD600": df["od600"].round(3), "pH probe": df["ph_probe"], "pH meter": df["ph_meter"],
            "Wet pellet (mg)": (df["pellet_recomputed_g"] * 1000).round(1), "Note": df["od_flag"].str.capitalize(),
        }), hide_index=True, width="stretch")
        st.subheader("Growth rate between samples")
        rates = kin["rates"]
        st.dataframe(pd.DataFrame({
            "From": rates["from_sample"].map(lambda s: f"S{s}"), "To": rates["to_sample"].map(lambda s: f"S{s}"),
            "μ (h⁻¹)": rates["mu_per_h"].round(2), "pH at end": rates["ph_probe_end"],
            "Phase": rates["phase"].str.capitalize(),
        }), hide_index=True, width="stretch")

    with process_tab:
        for chart in ("ph", "pellet_vs_od"):
            st.image(render_png(ALL_CHARTS[chart], kin, theme_key), width="stretch")

    with full_tab:
        st.caption(f"The downloadable report in the {THEMES[theme_key].label} theme.")
        st.iframe(build_html_report(record, findings, kin, theme_key), height=REPORT_HEIGHT)


if not current:
    welcome()
elif "error" in result:
    st.title("Batch Record Review")
    st.error(f"**{current[1]}** couldn't be analyzed. {result['error']}")
else:
    show_report(current[1], result)

"""FermentIQ upload app: upload a batch record, get the review report.

Run locally:  streamlit run app.py   (or double-click "Start FermentIQ App.bat")

Privacy: uploads are analyzed in memory for this browser session only. Nothing from the
file is saved to disk or shared between visitors; only an anonymous count is kept (fermentiq/usage.py).
"""

import io

import streamlit as st
import streamlit.components.v1 as components

from fermentiq import usage
from fermentiq.checks import run_checks
from fermentiq.html_report import build_html_report
from fermentiq.kinetics import analyze
from fermentiq.parse_record import parse_record
from fermentiq.report import run_id

REPORT_HEIGHT = 1600  # px; the embedded report scrolls inside this frame

st.set_page_config(page_title="FermentIQ", page_icon=":material/science:", layout="wide")


def review(file_bytes, file_name):
    """Run the full pipeline on one uploaded PDF, entirely in memory."""
    record = parse_record(io.BytesIO(file_bytes), source_name=file_name)
    findings = run_checks(record)
    kin = analyze(record)
    counts = findings["severity"].value_counts()
    return {
        "run_id": run_id(record),
        "html": build_html_report(record, findings, kin),
        "summary": ", ".join(f"{counts.get(s, 0)} {s}" for s in ("critical", "major", "minor")),
    }


def show_result(name, result):
    if "error" in result:
        st.error(f"**{name}** couldn't be analyzed. {result['error']}")
        return
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.success(f"**{name}** reviewed: {result['summary']} findings.")
    right.download_button("Download report", result["html"], file_name=f"{result['run_id']}_report.html",
                          mime="text/html", icon=":material/download:", use_container_width=True)
    components.html(result["html"], height=REPORT_HEIGHT, scrolling=True)


st.title("FermentIQ")
st.markdown("Upload a **BioFlo 120 batch record** (typed PDF) to get an automated review: calculation and "
            "documentation checks, plus growth kinetics. Each file gets its own report.")
st.caption(":material/lock: Files are analyzed in memory and never stored. Only an anonymous count of "
           "records checked is kept.")

uploads = st.file_uploader("Batch record PDF", type="pdf", accept_multiple_files=True)

# One result per uploaded file, kept only for this browser session.
results = st.session_state.setdefault("results", {})
current = {f.file_id for f in uploads}
for stale in set(results) - current:  # forget files the visitor removed
    del results[stale]

for f in uploads:
    if f.file_id not in results:
        with st.spinner(f"Reviewing {f.name}..."):
            try:
                results[f.file_id] = review(f.getvalue(), f.name)
                usage.record(success=True)
            except ValueError as error:  # FermentIQ's own plain-language messages
                results[f.file_id] = {"error": f"Reason: {error}."}
                usage.record(success=False)
            except Exception:  # damaged file, scan, or not a PDF: no technical traceback for visitors
                results[f.file_id] = {"error": "The file couldn't be read. Make sure it's the typed batch "
                                               "record PDF, not a scan or photo."}
                usage.record(success=False)

if len(uploads) == 1:
    show_result(uploads[0].name, results[uploads[0].file_id])
elif uploads:
    for tab, f in zip(st.tabs([f.name for f in uploads]), uploads):
        with tab:
            show_result(f.name, results[f.file_id])

st.divider()
st.caption(f"{usage.records_checked()} batch records checked so far · Works with the typed BioFlo 120 "
           "batch record form · Reports open in any browser; use Print → Save as PDF for a PDF copy.")

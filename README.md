# FermentIQ 🧫

**Automated batch-record review and growth analysis for bioreactor runs.**

> 🚧 Work in progress. I'm building this in public as a biomanufacturing student.

## The problem
Bioreactor runs are documented on paper-style batch records. Reviewing them by hand is slow, and
errors slip through: wrong calculations, inconsistent times, missing signatures, readings outside an
instrument's range. Turning the same record into growth kinetics usually means retyping it into a spreadsheet.

## What FermentIQ does
Give it a batch-record PDF and it:

**Module 1: Batch record checker** (data integrity and Good Documentation Practice)
- Re-checks every calculation: pellet weights, dilution-corrected absorbance
- Cross-checks time points against clock times and between pages
- Flags OD readings near the spectrophotometer limit, pH probe vs meter disagreement, and process deviations
- Flags biology inconsistencies (e.g. a Gram stain result that doesn't fit the organism)
- Finds GDP gaps: missing or unknown initials, blank required fields, unused rows not struck through,
  inconsistent formats, non-process notes

**Module 2: Growth kinetics**
- μmax from the steepest straight stretch of ln(OD600) vs time, plus doubling time
- Logistic growth fit (max OD, rate)
- Growth phase for each interval, alongside pH

**Output:** a Markdown report with findings ranked by severity, kinetics, charts and questions for review, plus CSV exports.

## Quick start
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

**Upload app:** double-click **`Start FermentIQ App.bat`** (or `streamlit run app.py`). The browser opens;
upload one or more batch-record PDFs and each gets its own report with a download button. Uploads are
analyzed in memory and never stored; only an anonymous count of records checked is kept.

**Run it on a folder:** put batch-record PDFs in `data/private/raw/`, then double-click **`Run FermentIQ.bat`**, or:
```bash
python -m fermentiq                     # every PDF in data/private/raw/
python -m fermentiq "path/to/record.pdf"   # just one PDF
python -m pytest                        # run the tests
```
Each PDF gets its own folder in `data/private/reports/<group>_<date>/` with `report.html`
(open in a browser; Ctrl+P → Save as PDF).
A PDF that can't be read is reported as failed without stopping the others.
Learning walkthrough: `notebooks/01_walkthrough.ipynb`

## Project layout
```
fermentiq/parse_record.py   PDF -> structured tables (keeps raw text for GDP checks)
fermentiq/checks.py         data-integrity and GDP checks -> findings
fermentiq/kinetics.py       mu_max, doubling time, logistic fit, phases
fermentiq/report.py         charts, observations, review questions
fermentiq/html_report.py    themed HTML report
fermentiq/settings.py       adjustable analysis settings
```

## Data
Built and tested on real *E. coli* runs in a BioFlo 120 bioreactor from my university lab.
Lab data, reports and data-specific tests stay in `data/private/` and `tests/private/` and are
**not** included in this repository.

## Roadmap
- [x] Parse batch-record PDFs, including highlighted Y/N selections
- [x] Data-integrity and GDP checks
- [x] Growth kinetics and report
- [ ] Streamlit app: upload a PDF, see findings and charts
- [ ] Multi-run comparison
- [ ] PDF report export, optional AI summary

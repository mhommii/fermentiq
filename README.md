# FermentIQ

**Automated batch record review and growth analysis for bioreactor runs.**

Upload a BioFlo 120 batch record (PDF) and FermentIQ re-checks every calculation and entry the way a QA
reviewer would, flags documentation gaps, works out the growth kinetics, and gives you a report in the theme
and format you choose.

Built by **Mohammad Hommam Ijaz** · [GitHub](https://github.com/mhommii) ·
[LinkedIn](https://www.linkedin.com/in/mohammad-hommam-ijaz/)

## The problem
Bioreactor runs are documented on paper-style batch records. Reviewing them by hand is slow, and errors slip
through: wrong calculations, inconsistent times, missing signatures, readings outside an instrument's range.
Turning the same record into growth kinetics usually means retyping it into a spreadsheet.

## What it does
**Batch record checker** (data integrity and Good Documentation Practice)
- Recalculates pellet weights and dilution-corrected absorbance
- Cross-checks time points against clock times and between pages
- Flags OD readings near the spectrophotometer limit, pH probe vs meter disagreement, and process deviations
- Checks Gram stain results against the organism's Gram type
- Finds GDP gaps: missing or unknown initials, self-verification, blank fields, unused rows not struck
  through, inconsistent dates, units and terminology

**Growth kinetics**
- μmax from the steepest straight stretch of ln(OD600), plus doubling time
- Logistic growth fit (maximum OD), growth phase for each interval, alongside pH

**Reports**
- Five themes: Classic, Dark, Print (black & white), Lab / clinical, Modern tech. Each restyles both the
  page and the charts, and all chart palettes are checked for colorblind safety.
- Downloads: HTML report, PDF report, Excel workbook (summary, findings, samples, raw tables, settings),
  and chart images

**Adjustable settings:** organism, Gram type, pellet culture volume, temperature setpoint and tolerance,
OD dilution limits and pH tolerance.

## Try it
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run app.py            # or double-click "Start FermentIQ App.bat"
```
In the browser, click **Try the sample record** or upload your own batch record.

**Command line** (one report folder per PDF, with HTML, PDF, Excel and chart images):
```bash
python -m fermentiq                          # every PDF in data/private/raw/
python -m fermentiq "record.pdf" --theme lab
```

## Privacy
- Uploads are analyzed in memory for your session only. Nothing from the file is saved or shown to anyone
  else; the app keeps only an anonymous count of records checked.
- The sample record in `samples/` is a real run with every identity removed: no institution logo or name,
  no metadata, initials replaced with neutral codes, group name and free-text notes removed. Measurements
  are unchanged. It was made with `scripts/make_public_sample.py`, which refuses to save the sample if
  anything identifying is left.
- Lab data, reports and data-specific tests live in `data/private/` and `tests/private/` and are never
  committed.

## Project layout
```
app.py                         Streamlit app (sidebar, tabs, themes, downloads)
fermentiq/parse_record.py      PDF -> structured tables (keeps raw text for GDP checks)
fermentiq/checks.py            data-integrity and GDP checks -> findings
fermentiq/kinetics.py          μmax, doubling time, logistic fit, phases
fermentiq/settings.py          adjustable analysis settings
fermentiq/style.py             report themes
fermentiq/charts.py            the four charts, drawn in any theme
fermentiq/html_report.py       themed HTML report
fermentiq/exports.py           PDF, Excel and chart-image downloads
scripts/make_public_sample.py  anonymized sample from a private record (dev only)
tests/                         public tests on the anonymized sample
```

## Development
```bash
pip install -r requirements-dev.txt
python -m pytest
```
Learning walkthrough: `notebooks/01_walkthrough.ipynb`

## License
Copyright (c) 2026 Mohammad Hommam Ijaz. All rights reserved. See [LICENSE](LICENSE).

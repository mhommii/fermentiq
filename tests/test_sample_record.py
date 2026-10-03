"""Public tests on the anonymized sample batch record (samples/sample_batch_record.pdf).

The sample is a real run with every identity masked; its measurements are unchanged.
Run from the project folder:  python -m pytest
"""

import io
import zipfile
from html import escape
from pathlib import Path

import pdfplumber
import pytest

from fermentiq.checks import run_checks
from fermentiq.exports import build_chart_zip, build_excel, build_pdf
from fermentiq.html_report import build_html_report
from fermentiq.kinetics import analyze
from fermentiq.parse_record import parse_record
from fermentiq.settings import AnalysisSettings
from fermentiq.style import THEMES

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "sample_batch_record.pdf"


@pytest.fixture(scope="module")
def record():
    return parse_record(SAMPLE)


@pytest.fixture(scope="module")
def findings(record):
    return run_checks(record)


@pytest.fixture(scope="module")
def kin(record):
    return analyze(record)


def flagged(findings, check):
    return set(findings.loc[findings["check"] == check, "sample"].astype(str))


def test_sample_is_anonymized(record):
    with pdfplumber.open(SAMPLE) as pdf:
        assert not any(page.images for page in pdf.pages), "logo/images must be removed"
        assert not any(v for k, v in pdf.metadata.items() if k not in ("Producer",)), pdf.metadata
    assert record.header["group_id"] == "Group A"
    assert all(len(m) == 2 and m.startswith("P") for m in record.header["members"])
    assert record.notes == []


def test_parsed_values(record):
    proc = record.process.set_index("sample")
    assert proc.loc[1, "ph_probe"] == 6.79 and proc.loc[1, "ph_meter"] == 6.65
    assert proc["used"].sum() == 9
    od = record.od.set_index("sample")
    assert od.loc[7, "a_raw_1"] == 1.057 and od.loc[7, "df_1"] == 2 and od.loc[7, "a_corrected_1"] == 1.320
    pel = record.pellets.set_index("sample")
    assert pel.loc[2, "tube_pellet_g"] == 1.407
    assert (pel.loc[1:9, "gram_performed"] == "Y").all()  # highlighted choices survive anonymization


def test_findings(findings):
    assert findings["severity"].value_counts().to_dict() == {"critical": 4, "major": 10, "minor": 12}
    assert flagged(findings, "pellet_calc") == {"2", "3", "9"}
    assert flagged(findings, "time_cross_page") == {"3"}
    assert flagged(findings, "od_near_saturation") == {"5", "6"}
    assert flagged(findings, "gram_inconsistent") == {"3"}
    assert flagged(findings, "initials_missing") == {"4"}


def test_gram_type_setting(record):
    positive = run_checks(record, AnalysisSettings(gram_type="positive"))
    assert flagged(positive, "gram_inconsistent") == {"6", "9"}
    skipped = run_checks(record, AnalysisSettings(gram_type="not applicable"))
    assert flagged(skipped, "gram_inconsistent") == set()


def test_kinetics(kin):
    assert kin["mu_max"]["mu_max_per_h"] == pytest.approx(0.80, abs=0.02)
    assert kin["mu_max"]["doubling_time_min"] == pytest.approx(52, abs=2)
    assert kin["logistic"]["K_od"] == pytest.approx(1.41, abs=0.05)


@pytest.mark.parametrize("theme", list(THEMES))
def test_reports_in_every_theme(record, findings, kin, theme):
    assert escape(THEMES[theme].label) in build_html_report(record, findings, kin, theme)
    assert build_pdf(record, findings, kin, theme).startswith(b"%PDF")
    charts = zipfile.ZipFile(io.BytesIO(build_chart_zip(kin, theme))).namelist()
    assert len(charts) == 4


def test_excel(record, findings, kin):
    workbook = zipfile.ZipFile(io.BytesIO(build_excel(record, findings, kin)))
    assert "xl/workbook.xml" in workbook.namelist()

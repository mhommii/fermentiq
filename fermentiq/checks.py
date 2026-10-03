"""Data-integrity and Good Documentation Practice (GDP) checks for a batch record.

Each check looks at the parsed record and returns Findings. Severity levels:
  critical - a recorded number is wrong (affects results)
  major    - a procedure/documentation gap a QA reviewer would reject
  minor    - a style/consistency issue to fix next time
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .settings import AnalysisSettings

SEVERITY_ORDER = ["critical", "major", "minor"]


@dataclass
class Finding:
    check: str
    severity: str
    sample: object   # sample number, or "all" / "-"
    field: str
    recorded: str
    expected: str
    message: str


def used(df):
    return df[df["used"]] if len(df) else df


# ---------- calculations ----------

def check_pellet_math(record, cfg):
    findings = []
    p = used(record.pellets)
    for _, row in p.iterrows():
        actual = row["tube_pellet_g"] - row["tube_g"]
        if actual < 0:
            findings.append(Finding(
                "pellet_negative", "critical", row["sample"], "tube_pellet_g",
                f"{row['tube_pellet_g']:.4f} g", f"> {row['tube_g']:.4f} g",
                "Tube + pellet weighs LESS than the empty tube, so one of the weights is wrong."))
        if abs(actual - row["pellet_g"]) > cfg.pellet_tolerance_g:
            findings.append(Finding(
                "pellet_calc", "critical", row["sample"], "pellet_g",
                f"{row['pellet_g']:.4f} g", f"{actual:.4f} g",
                f"Calculated pellet weight doesn't match {row['tube_pellet_g']:.4f} - {row['tube_g']:.4f}."))
    return findings


def check_copied_values(record, cfg):
    """A tube weight identical to the previous sample's tube+pellet weight is a likely copy error."""
    findings = []
    p = used(record.pellets).reset_index(drop=True)
    for i in range(1, len(p)):
        if p.loc[i, "tube_g"] == p.loc[i - 1, "tube_pellet_g"]:
            findings.append(Finding(
                "copied_value", "major", p.loc[i, "sample"], "tube_g",
                f"{p.loc[i, 'tube_g']:.4f} g", "an independent weighing",
                f"Tube weight equals sample {p.loc[i - 1, 'sample']}'s tube+pellet weight, "
                "which suggests it was copied rather than weighed."))
    return findings


def check_od(record, cfg):
    findings = []
    od = used(record.od)
    for _, row in od.iterrows():
        a, df = row["a_raw_1"], row["df_1"]
        if a >= cfg.od_linear_limit and df == 1:
            findings.append(Finding(
                "od_not_diluted", "major", row["sample"], "a_raw_1", f"{a:.3f}", "diluted",
                "Absorbance >= 1.0 but no dilution was made."))
        elif cfg.od_warning_level <= a < cfg.od_linear_limit and df == 1:
            findings.append(Finding(
                "od_near_saturation", "major", row["sample"], "a_raw_1", f"{a:.3f}",
                f"< {cfg.od_warning_level} or diluted",
                "Reading is close to the spectrophotometer's linear limit and was not diluted, "
                "so it is probably underestimated. Compare undiluted vs diluted readings of later samples."))
        if df > 1:
            if np.isnan(row["a_corrected_1"]):
                findings.append(Finding("od_corrected_missing", "major", row["sample"], "a_corrected_1",
                                        row["raw_a_corrected_1"] or "blank", "DF x A", "Diluted sample has no corrected absorbance."))
            elif not np.isnan(row["a_diluted_1"]) and abs(row["a_diluted_1"] * df - row["a_corrected_1"]) > 0.002:
                findings.append(Finding(
                    "od_corrected_calc", "critical", row["sample"], "a_corrected_1",
                    f"{row['a_corrected_1']:.3f}", f"{row['a_diluted_1'] * df:.3f}",
                    "Corrected absorbance doesn't equal DF x diluted absorbance."))
    undiluted_na = od[(od["df_1"] == 1) & (od["raw_a_corrected_1"].str.upper() == "N/A")]
    if len(undiluted_na):
        findings.append(Finding(
            "od_corrected_na", "minor", ", ".join(map(str, undiluted_na["sample"])), "a_corrected_1",
            "N/A", "same as A (DF = 1)",
            "Corrected absorbance column is 'N/A' for undiluted samples. With DF = 1 it should repeat A, "
            "so the final value is recorded in one consistent column."))
    if (od["raw_a_raw_2"].str.upper().isin(["N/A", ""])).all():
        findings.append(Finding(
            "od_replicate_missing", "major", "all", "a_raw_2", "N/A for every sample", "a second measurement",
            "The form says two separate samples are measured for absorbance, but replicate #2 was never "
            "recorded. Without replicates there's no estimate of measurement error."))
    return findings


# ---------- time ----------

def check_times(record, cfg):
    findings = []
    proc = used(record.process)
    start = proc["clock_min"].iloc[0]
    for _, row in proc.iterrows():
        elapsed = row["clock_min"] - start
        if abs(elapsed - row["time_point_min"]) > cfg.time_tolerance_min:
            findings.append(Finding(
                "time_vs_clock", "major", row["sample"], "time_point",
                f"{row['time_point_min']:.0f} min", f"{elapsed:.0f} min (from clock time)",
                "Recorded time point doesn't match the elapsed clock time."))
    merged = proc.merge(used(record.od), on="sample", suffixes=("_process", "_od"))
    for _, row in merged.iterrows():
        if abs(row["time_point_min_process"] - row["time_point_min_od"]) > cfg.time_tolerance_min:
            elapsed = row["clock_min"] - start
            findings.append(Finding(
                "time_cross_page", "major", row["sample"], "time_point",
                f"{row['time_point_min_od']:.0f} min on OD page",
                f"{row['time_point_min_process']:.0f} min on process page (clock: {elapsed:.0f} min)",
                "The same sample has different time points on different pages."))
    no_unit = [str(r["sample"]) for t in (proc, used(record.od)) for _, r in t.iterrows()
               if "min" not in r["raw_time_point"]]
    if no_unit:
        findings.append(Finding("time_units", "minor", ", ".join(sorted(set(no_unit), key=int)), "time_point",
                                "number without unit", "e.g. 'T = 332 min'", "Time point written without units."))
    return findings


# ---------- process ----------

def check_process(record, cfg):
    findings = []
    proc = used(record.process)
    offset = proc["ph_probe"] - proc["ph_meter"]
    if (offset.abs() > cfg.ph_offset_tolerance).any():
        findings.append(Finding(
            "ph_offset", "major", "all", "ph_probe vs ph_meter",
            f"probe higher by {offset.min():.2f}-{offset.max():.2f} (mean {offset.mean():.2f})",
            f"within ±{cfg.ph_offset_tolerance}",
            "The bioreactor pH probe and the bench pH meter disagree throughout the run. "
            "One of them (often the in-line probe) needs recalibration."))
    for _, row in proc.iterrows():
        if abs(row["temp_c"] - cfg.temp_setpoint_c) > cfg.temp_tolerance_c:
            findings.append(Finding("temp_deviation", "major", row["sample"], "temp_c", f"{row['temp_c']}",
                                    f"{cfg.temp_setpoint_c} ± {cfg.temp_tolerance_c}", "Temperature out of range."))
    for col in ("rpm", "gas_slpm"):
        if proc[col].nunique() > 1:
            findings.append(Finding("setpoint_change", "major", "all", col, str(sorted(proc[col].unique())),
                                    "constant", f"{col} changed during the run; document the reason."))
    return findings


def check_pellet_vs_od(record, cfg):
    """Cell mass should rise with OD. If it doesn't, the pellet method is unreliable."""
    p = used(record.pellets).merge(used(record.od), on="sample")
    p["pellet_actual"] = p["tube_pellet_g"] - p["tube_g"]
    p["od"] = np.where(p["df_1"] > 1, p["a_corrected_1"], p["a_raw_1"])
    valid = p[p["pellet_actual"] > 0]
    if len(valid) < 4:
        return []
    r = np.corrcoef(valid["od"], valid["pellet_actual"])[0, 1]
    if r < 0.5:
        low, high = valid["pellet_actual"].min() * 1000, valid["pellet_actual"].max() * 1000
        return [Finding(
            "pellet_vs_od", "major", "all", "pellet_g", f"correlation with OD r = {r:.2f}", "r close to 1",
            "Pellet weights don't rise with OD600. As a rough rule of thumb, OD600 = 1 is only ~1-2 mg of wet "
            f"E. coli per mL; these pellets are {low:.0f}-{high:.0f} mg. Leftover medium or weighing variation "
            "may dominate. Remove supernatant completely, or use a larger volume / dry cell weight.")]
    return []


def check_gram(record, cfg):
    findings = []
    p = used(record.pellets)
    organism = cfg.organism_for(record) or "The organism"
    # the stain color that contradicts the expected Gram type
    wrong_color = {"negative": ("purple", "pink/red (Gram-negative)",
                                "Purple suggests under-decolorization or a staining step was missed."),
                   "positive": ("pink", "purple (Gram-positive)",
                                "Pink suggests over-decolorization or an old culture losing Gram-positivity.")}
    for _, row in p.iterrows():
        obs = row["raw_gram_observations"].lower()
        if cfg.gram_type in wrong_color and wrong_color[cfg.gram_type][0] in obs:
            color, expected, cause = wrong_color[cfg.gram_type]
            findings.append(Finding(
                "gram_inconsistent", "major", row["sample"], "gram_observations",
                row["raw_gram_observations"].replace("\n", " "), expected,
                f"{organism} is Gram-{cfg.gram_type} and should stain {expected.split(' ')[0]}. {cause}"))
        if row["gram_performed"] not in ("Y", "N"):
            findings.append(Finding("gram_selection_missing", "minor", row["sample"], "gram_performed",
                                    "nothing selected", "Y or N", "Gram stain Y/N not selected."))
    selected_by_highlight = p["gram_performed"].isin(["Y", "N"]).all()
    if selected_by_highlight and len(p):
        findings.append(Finding(
            "highlight_selection", "minor", "all", "gram_performed", "Y chosen by yellow highlight",
            "circle the choice and strike through the other",
            "Highlighting isn't a GDP-compliant way to record a choice. It may not show on copies or scans."))
    return findings


# ---------- Good Documentation Practice ----------

def normalize_initials(text):
    return re.sub(r"[.\s]", "", text.upper())


def check_signatures(record, cfg):
    findings = []
    sig = record.signatures
    used_samples = {
        "process": set(used(record.process)["sample"]),
        "pellet": set(used(record.pellets)["sample"]),
        "od": set(used(record.od)["sample"]),
    }
    sig = sig[sig.apply(lambda r: r["sample"] in used_samples[r["table"]], axis=1)]

    for _, row in sig.iterrows():
        missing = [who for who in ("operator", "verifier") if not row[who]]
        if missing:
            findings.append(Finding(
                "initials_missing", "major", row["sample"], f"{row['table']}.{row['field']}",
                row["raw"].replace("Operator/Verifier", "").strip() or "blank", "operator/verifier",
                f"Missing {' and '.join(missing)} initials."))
        elif normalize_initials(row["operator"]) == normalize_initials(row["verifier"]):
            findings.append(Finding(
                "self_verified", "major", row["sample"], f"{row['table']}.{row['field']}",
                f"{row['operator']}/{row['verifier']}", "two different people",
                "Operator and verifier are the same person."))

    members = {normalize_initials(m) for m in record.header.get("members", [])}
    unknown = {}
    for _, row in sig.iterrows():
        for person in (row["operator"], row["verifier"]):
            for token in re.split(r"[,\s]+", person.replace(".", "")):
                if token and normalize_initials(token) not in members:
                    unknown.setdefault(token, set()).add(row["sample"])
    for token, samples in sorted(unknown.items()):
        findings.append(Finding(
            "initials_unknown", "minor", ", ".join(map(str, sorted(samples))), "initials", token,
            "a name on the group member list",
            f"Initials '{token}' are not on the GROUP MEMBERS list. Add them, or correct a typo."))
    return findings


def check_header(record, cfg):
    findings = []
    if not record.header.get("serial_number"):
        findings.append(Finding(
            "serial_blank", "major", "-", "serial_number", "blank", "bioreactor serial #",
            "Equipment serial number is blank, so the run can't be traced to a specific bioreactor."))
    return findings


def check_unused_rows(record, cfg):
    findings = []
    for name, df in (("process", record.process), ("pellet", record.pellets), ("od", record.od)):
        unused = df[~df["used"]]
        if len(unused):
            findings.append(Finding(
                "unused_rows", "minor", ", ".join(map(str, unused["sample"])), f"{name} table",
                "left blank", "struck through with a line, initials and date",
                "Unused rows should be struck through so nothing can be added later."))
    return findings


def check_formats(record, cfg):
    findings = []
    dates = pd.concat([used(record.process)[["sample", "raw_date"]], used(record.od)[["sample", "raw_date"]]])
    bad = dates[~dates["raw_date"].str.match(r"^\d{2}/\d{2}/\d{2}$")]
    if len(bad):
        findings.append(Finding("date_format", "minor", ", ".join(map(str, sorted(set(bad["sample"])))),
                                "date", ", ".join(sorted(set(bad["raw_date"]))), "DD/MM/YY",
                                "Date not written in the form's DD/MM/YY format."))

    p = used(record.pellets)
    with_units = p[p["raw_tube_g"].str.contains(r"[a-zA-Z]", regex=True)]
    if len(with_units):
        findings.append(Finding("units_in_value", "minor", ", ".join(map(str, with_units["sample"])), "tube_g",
                                ", ".join(with_units["raw_tube_g"]), "number only (unit is in the header)",
                                "Units written inside numeric cells. This is inconsistent with other rows."))

    terms = p["raw_streak"].str.replace("\n", " ").unique()
    if len(terms) > 1:
        findings.append(Finding(
            "inconsistent_terms", "minor", "all", "streak", "; ".join(terms), "one standard entry (e.g. 'Performed')",
            "Quadrant streak was recorded with many different, informal words. Use one standard term."))

    od = used(record.od)
    blank = od[(od["raw_notes"] == "") | (od["raw_a_corrected_2"] == "")]
    if len(blank):
        findings.append(Finding("blank_cells", "minor", ", ".join(map(str, blank["sample"])), "od notes / corrected #2",
                                "blank", "N/A", "Empty cells in used rows should say N/A."))
    return findings



ALL_CHECKS = [
    check_header, check_pellet_math, check_copied_values, check_od, check_times, check_process,
    check_pellet_vs_od, check_gram, check_signatures, check_unused_rows, check_formats,
]


def run_checks(record, cfg=None):
    """Run every check and return the findings as a DataFrame, most severe first."""
    cfg = cfg or AnalysisSettings()
    findings = [f for check in ALL_CHECKS for f in check(record, cfg)]
    df = pd.DataFrame([f.__dict__ for f in findings])
    if len(df):
        df["severity"] = pd.Categorical(df["severity"], SEVERITY_ORDER, ordered=True)
        df = df.sort_values(["severity", "check"], kind="stable").reset_index(drop=True)
    return df

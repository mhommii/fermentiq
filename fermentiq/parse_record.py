"""Read a BioFlo 120 batch-record PDF into structured tables.

The batch record has three kinds of tables:
  * process table   (pages 1, 3): time, clock, RPM, temperature, pH, gas flow
  * pellet table    (pages 4-8):  tube weights, pellet weight, streak, Gram stain
  * OD table        (pages 9-10): absorbance at 600 nm, dilution factor
Every sample takes two rows in a table: one with the values, and one
underneath with the operator/verifier initials for each value.

We keep the RAW text of every cell next to the parsed number, because the
documentation checks need to see exactly what was written (e.g. "1.5267g").
"""

import re
from dataclasses import dataclass, field

import pandas as pd
import pdfplumber

# Column keyword -> our field name. A column is found by searching its header text.
PROCESS_COLUMNS = {
    "date": "Date",
    "time_point": "Time Point",
    "clock_time": "Clock Time",
    "rpm": "Agitation",
    "temp_c": "Temperature",
    "ph_probe": "pH Reading",
    "ph_meter": "pH Measured",
    "gas_slpm": "Gas Flow",
    "notes": "Notes",
}
PELLET_COLUMNS = {
    "tube_g": "Tube Weight",
    "tube_pellet_g": "Tube with Pellet",
    "pellet_g": "Calculated Pellet",
    "streak": "Quadrant Streak",
    "gram_observations": "Observations",
    "comments": "Comments",
}
OD_COLUMNS = {
    "date": "Date",
    "time_point": "Time Point",
    "a_raw": "Absorbance",
    "df": "Dilution Factor",
    "a_corrected": "Corrected",
    "notes": "Notes",
}

YELLOW = (1.0, 1.0, 0.0)
INITIALS_ONLY = re.compile(r"^[A-Z.\s,]*/[A-Z.\s,]*$")  # e.g. "AB/CD", "/EF GH", "/"


@dataclass
class BatchRecord:
    source: str
    header: dict
    process: pd.DataFrame
    pellets: pd.DataFrame
    od: pd.DataFrame
    signatures: pd.DataFrame  # one row per value cell: table, sample, field, operator, verifier
    notes: list = field(default_factory=list)  # free text from the NOTES boxes


# ---------- small helpers for messy cell text ----------

def clean(cell):
    """Turn a table cell into a stripped string ('' for empty)."""
    return "" if cell is None else str(cell).strip()


def to_number(text):
    """First number in the text: '1.5267g' -> 1.5267, 'T= 361 min' -> 361, 'N/A' -> NaN."""
    match = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else float("nan")


def clock_to_minutes(text):
    """Military time '0945' -> 585 minutes after midnight."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) not in (3, 4):
        return float("nan")
    return int(digits[:-2]) * 60 + int(digits[-2:])


def replicate_value(cell, n):
    """OD cells look like 'Sample #1\\n0.172'. Return the text written for replicate n."""
    text = clean(cell)
    return text.replace(f"Sample #{n}", "").strip()


def split_initials(cell):
    """'Operator/Verifier\\nAB /CD' -> ('AB', 'CD'). Missing parts come back as ''."""
    text = clean(cell).replace("Operator/Verifier", "").strip()
    if "/" not in text:
        return text, ""
    operator, verifier = text.split("/", 1)
    return operator.strip(), verifier.strip()


def is_signature_row(row):
    cells = [clean(c) for c in row]
    form_placeholders = {"N/A", "Y/N"}  # look like initials ("N/A") but are printed on the form
    return any("Operator/Verifier" in c for c in cells) or any(
        c and c.replace(" ", "") not in form_placeholders and INITIALS_ONLY.match(c)
        for c in cells
    )


def find_columns(header_row, keywords):
    """Map our field names to column positions using the header text."""
    positions = {}
    for name, keyword in keywords.items():
        for i, cell in enumerate(header_row):
            if keyword.lower() in clean(cell).lower().replace("\n", " "):
                positions[name] = i
                break
    return positions


def highlighted_choice(page, row_bbox):
    """Return 'Y' or 'N' if that letter is highlighted yellow inside the row, else ''."""
    x0, top, x1, bottom = row_bbox
    letters = [w for w in page.extract_words() if w["text"] in ("Y", "N")
               and top <= w["top"] <= bottom]
    for rect in page.rects:
        color = rect.get("non_stroking_color")
        if not isinstance(color, (tuple, list)) or tuple(color) != YELLOW:  # greyscale fills are plain floats
            continue
        for w in letters:
            if rect["x0"] - 1 <= w["x0"] <= rect["x1"] + 1 and rect["top"] - 2 <= w["top"] <= rect["bottom"]:
                return w["text"]
    return ""


# ---------- main parser ----------

def parse_record(pdf_path, source_name=None):
    """`pdf_path` can be a file path or an open file (e.g. an upload held in memory)."""
    process_rows, pellet_rows, od_rows, signatures, notes = [], [], [], [], []
    header_info = {}
    counters = {"process": 0, "od": 0}
    last_sample = {"process": None, "pellet": None, "od": None}

    def add_signatures(table, sample, row, columns):
        for name, idx in columns.items():
            if idx >= len(row) or row[idx] is None:
                continue
            operator, verifier = split_initials(row[idx])
            existing = next((s for s in signatures if s["table"] == table
                             and s["sample"] == sample and s["field"] == name), None)
            if existing:  # a signature row split across two pages: fill the blanks
                existing["operator"] = existing["operator"] or operator
                existing["verifier"] = existing["verifier"] or verifier
            else:
                signatures.append({"table": table, "sample": sample, "field": name,
                                   "operator": operator, "verifier": verifier,
                                   "raw": clean(row[idx])})

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if page_no == 1:
                header_info = parse_header(text)
            if "NOTES:" in text:
                note = text.split("NOTES:", 1)[1].strip()
                if note:
                    notes.append({"page": page_no, "text": note})

            tables = page.find_tables()
            if not tables:
                continue
            table = max(tables, key=lambda t: len(t.rows))  # the main form table, not a header fragment
            rows = table.extract()
            header = " ".join(clean(c) for c in rows[0])

            if "Clock Time" in header:
                kind, keywords = "process", PROCESS_COLUMNS
            elif "Microcentrifuge" in header:
                kind, keywords = "pellet", PELLET_COLUMNS
            elif "Absorbance" in header:
                kind, keywords = "od", OD_COLUMNS
            else:
                continue
            cols = find_columns(rows[0], keywords)

            for row, row_obj in zip(rows[1:], table.rows[1:]):
                if is_signature_row(row):
                    if last_sample[kind] is not None:
                        sig_cols = dict(cols)
                        if kind == "pellet":
                            sig_cols["gram_performed"] = cols["streak"] + 1
                        add_signatures(kind, last_sample[kind], row, sig_cols)
                    continue

                if kind == "pellet":
                    first = clean(row[0])
                    if not first.isdigit():
                        continue
                    sample = int(first)
                    record = {"sample": sample}
                    for name, idx in cols.items():
                        record[f"raw_{name}"] = clean(row[idx])
                    record["raw_gram_performed"] = clean(row[cols["streak"] + 1])
                    record["gram_performed"] = highlighted_choice(page, row_obj.bbox)
                    for name in ("tube_g", "tube_pellet_g", "pellet_g"):
                        record[name] = to_number(record[f"raw_{name}"])
                    # "used" = a weight was actually recorded (footnote text can spill into empty rows)
                    record["used"] = not (pd.isna(record["tube_g"]) and pd.isna(record["tube_pellet_g"]))
                    pellet_rows.append(record)
                    last_sample["pellet"] = sample
                    continue

                if row[cols["date"]] is None:  # a leftover piece of the rotated "Sample N" label
                    continue
                counters[kind] += 1
                sample = counters[kind]
                record = {"sample": sample}

                if kind == "process":
                    for name, idx in cols.items():
                        record[f"raw_{name}"] = clean(row[idx])
                    record["time_point_min"] = to_number(record["raw_time_point"])
                    record["clock_min"] = clock_to_minutes(record["raw_clock_time"])
                    for name in ("rpm", "temp_c", "ph_probe", "ph_meter", "gas_slpm"):
                        record[name] = to_number(record[f"raw_{name}"])
                    record["used"] = bool(record["raw_date"] or record["raw_time_point"])
                    process_rows.append(record)
                else:  # OD table: each value column has replicate #1 and #2 side by side
                    record["raw_date"] = clean(row[cols["date"]])
                    record["raw_time_point"] = clean(row[cols["time_point"]])
                    record["raw_notes"] = clean(row[cols["notes"]])
                    record["time_point_min"] = to_number(record["raw_time_point"])
                    for name in ("a_raw", "df", "a_corrected"):
                        for rep in (1, 2):
                            raw = replicate_value(row[cols[name] + rep - 1], rep)
                            record[f"raw_{name}_{rep}"] = raw
                            record[f"{name}_{rep}"] = to_number(raw)
                    # e.g. "0.660 x 2 = 1.320" -> absorbance of the diluted sample = 0.660
                    calc = re.search(r"(\d*\.?\d+)\s*[x×*]\s*(\d*\.?\d+)\s*=\s*(\d*\.?\d+)",
                                     record["raw_notes"])
                    record["a_diluted_1"] = float(calc.group(1)) if calc else float("nan")
                    record["used"] = bool(record["raw_date"] or record["raw_time_point"])
                    od_rows.append(record)
                last_sample[kind] = sample

    missing = [name for name, rows in (("process", process_rows), ("pellet", pellet_rows), ("OD600", od_rows))
               if not rows]
    if missing:
        raise ValueError(f"doesn't look like a BioFlo 120 batch record: no {', '.join(missing)} table found")

    return BatchRecord(
        source=source_name or str(pdf_path),
        header=header_info,
        process=pd.DataFrame(process_rows),
        pellets=pd.DataFrame(pellet_rows),
        od=pd.DataFrame(od_rows),
        signatures=pd.DataFrame(signatures),
        notes=notes,
    )


def parse_header(page_text):
    def grab(pattern):
        match = re.search(pattern, page_text)
        return match.group(1).strip("_ ").strip() if match else ""

    members = grab(r"GROUP MEMBERS \(INITIALS\):\s*(.*)")
    return {
        "organism": grab(r"BATCH RECORD for (.+?) GROWTH"),
        "equipment": grab(r"GROWTH in (.+)"),
        "serial_number": grab(r"SERIAL #\s*(.*)"),
        "group_id": grab(r"GROUP ID:\s*(.*?)\s+GROUP MEMBERS"),
        "members": [m.strip() for m in members.split(",") if m.strip()],
    }

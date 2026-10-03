"""Make the anonymized public sample from a private batch record.

    python scripts/make_public_sample.py ["data/private/raw/<record>.pdf"]

Developer tool (needs PyMuPDF from requirements-dev.txt; the app doesn't use it). It writes
samples/sample_batch_record.pdf with:
  * the logo image removed from every page (it carries the institution's name)
  * all document metadata removed (author, dates, XMP)
  * every set of initials replaced by a neutral code (PA, PB, ...), consistently across pages
  * the group name replaced ("Group A") and free-text notes removed
Measurements, layout, table lines and highlighted choices are left untouched.
Then it re-checks the output and refuses to keep it if anything identifying is left.
"""

import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fermentiq.checks import run_checks  # noqa: E402
from fermentiq.kinetics import analyze  # noqa: E402
from fermentiq.parse_record import parse_record  # noqa: E402

OUT = ROOT / "samples" / "sample_batch_record.pdf"
PUBLIC_GROUP = "Group A"


def person_codes(record):
    """Every set of initials in the record (member list + all signatures) -> PA, PB, ...

    Letters only: FermentIQ recognizes stand-alone initials rows by letters, so codes must not contain digits.
    """
    tokens = list(record.header["members"])
    for column in ("operator", "verifier"):
        for value in record.signatures[column]:
            tokens += re.split(r"[\s,/]+", value)
    codes = {}
    for token in tokens:
        key = token.replace(".", "").strip()
        if key and key not in codes:
            codes[key] = "P" + chr(ord("A") + len(codes))
    return codes


def initials_pattern(codes):
    # longest first so "ABC" is matched before "BC"; letters may be written with dots ("A.B")
    alternatives = [r"\.?\s?".join(map(re.escape, key)) for key in sorted(codes, key=len, reverse=True)]
    return re.compile(r"(?<![A-Za-z])(" + "|".join(alternatives) + r")(?![A-Za-z])")


def holds_initials(line_text):
    """Only touch signature cells and the member list, never measurements or form text."""
    if "GROUP MEMBERS" in line_text:
        return True
    rest = line_text.replace("Operator/Verifier", "").strip()
    return "/" in rest and re.fullmatch(r"[A-Z.\s,/]+", rest) is not None


def redact_page(page, pattern, codes, notes, group):
    for xref in {img[0] for img in page.get_images(full=True)}:  # logo
        for rect in page.get_image_rects(xref):
            page.add_redact_annot(rect, fill=False)

    for note in notes:  # free-text notes are not part of the record's data
        for line in note.splitlines():
            for rect in page.search_for(line.strip()):
                page.add_redact_annot(rect, fill=False)

    for rect in page.search_for(group) if group else []:
        page.add_redact_annot(rect, text=PUBLIC_GROUP, fontname="helv", fontsize=10, fill=False)

    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chars = [c for span in line["spans"] for c in span["chars"]]
            text = "".join(c["c"] for c in chars)
            if not holds_initials(text):
                continue
            start_at = text.find("(INITIALS):") + 1 if "GROUP MEMBERS" in text else 0
            for match in pattern.finditer(text, start_at):
                hit = chars[match.start():match.end()]
                rect = pymupdf.Rect(hit[0]["bbox"]) | pymupdf.Rect(hit[-1]["bbox"])
                shrink = (rect.width / len(hit)) * 0.15  # stay clear of the neighbouring "/" or ","
                rect = pymupdf.Rect(rect.x0 + shrink, rect.y0, rect.x1 - shrink, rect.y1)
                size = line["spans"][0]["size"]
                code = codes[re.sub(r"[.\s]", "", match.group())]
                page.add_redact_annot(rect, text=code, fontname="helv", fontsize=size * 0.85, fill=False)

    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)  # keep table lines and highlights


def verify(original, codes):
    """Fail loudly if anything identifying survived, or if the data changed."""
    doc = pymupdf.open(OUT)
    problems = []
    if any(v for k, v in doc.metadata.items() if k not in ("format", "encryption")):
        problems.append(f"metadata left: {doc.metadata}")
    if doc.get_xml_metadata():
        problems.append("XMP metadata left")
    if any(page.get_images() for page in doc):
        problems.append("images left")
    text = "\n".join(page.get_text() for page in doc)
    leftover = sorted({m.group() for m in initials_pattern(codes).finditer(text)})
    if leftover:
        problems.append(f"initials left: {leftover}")
    for phrase in [original.header["group_id"]] + [n["text"].splitlines()[0] for n in original.notes]:
        if phrase and phrase in text:
            problems.append(f"text left: {phrase!r}")
    raw = OUT.read_bytes().lower()
    author = (pymupdf.open(original.source).metadata.get("author") or "").lower().encode()
    if author and author in raw:
        problems.append("original author name still in file bytes")

    sample = parse_record(OUT)
    for table in ("process", "od", "pellets"):
        before, after = getattr(original, table), getattr(sample, table)
        numeric = [c for c in before.columns if not c.startswith("raw_") and before[c].dtype.kind == "f"]
        if not before[numeric].equals(after[numeric]):
            problems.append(f"{table} measurements changed")
    counts = lambda r: run_checks(r)["severity"].value_counts().to_dict()
    if counts(original) != counts(sample):
        problems.append(f"finding counts changed: {counts(original)} -> {counts(sample)}")
    if round(analyze(original)["mu_max"]["mu_max_per_h"], 6) != round(analyze(sample)["mu_max"]["mu_max_per_h"], 6):
        problems.append("mu_max changed")
    return problems


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((ROOT / "data/private/raw").glob("*.pdf"))[0]
    original = parse_record(source)
    codes = person_codes(original)
    pattern = initials_pattern(codes)

    doc = pymupdf.open(source)
    for page in doc:
        redact_page(page, pattern, codes, [n["text"] for n in original.notes], original.header["group_id"])
    doc.set_metadata({})
    doc.del_xml_metadata()
    OUT.parent.mkdir(exist_ok=True)
    doc.save(OUT, garbage=4, deflate=True, clean=True)  # garbage=4 drops the removed logo objects

    problems = verify(original, codes)
    if problems:
        OUT.unlink()
        sys.exit("Sample NOT created:\n  " + "\n  ".join(problems))
    print(f"Created {OUT.relative_to(ROOT)}: {len(codes)} people replaced with codes, logo, metadata, "
          "group name and notes removed; measurements and findings unchanged.")


if __name__ == "__main__":
    main()

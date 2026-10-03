"""Run FermentIQ on batch-record PDFs. Each PDF gets its own report.

    python -m fermentiq                    every PDF in data/private/raw/
    python -m fermentiq "record.pdf"       one PDF
    python -m fermentiq "some/folder"      every PDF in that folder
"""

import argparse
import sys
from pathlib import Path

from .checks import run_checks
from .html_report import write_html_report
from .kinetics import analyze
from .parse_record import parse_record
from .report import run_id
from .style import DEFAULT_THEME, THEMES

DEFAULT_INPUT = Path("data/private/raw")


def find_pdfs(target):
    target = Path(target)
    if target.is_dir():
        return sorted(target.glob("*.pdf"))
    if target.suffix.lower() == ".pdf" and target.exists():
        return [target]
    raise SystemExit(f"Not a PDF or folder: {target}")


def process(pdf, out_dir, used_ids, theme=DEFAULT_THEME):
    """Run the full pipeline on one PDF and return a one-line summary."""
    record = parse_record(pdf)
    findings = run_checks(record)
    kin = analyze(record)

    rid = run_id(record)
    base, n = rid, 2
    while rid in used_ids:  # two PDFs from the same group and day must not overwrite each other
        rid, n = f"{base}-{n}", n + 1
    used_ids.add(rid)

    html = write_html_report(record, findings, kin, out_dir, rid, theme)
    counts = findings["severity"].value_counts()
    return {
        "run": rid,
        "findings": "/".join(str(counts.get(s, 0)) for s in ("critical", "major", "minor")),
        "mu_max": f"{kin['mu_max']['mu_max_per_h']:.2f}",
        "report": html,
    }


def main():
    parser = argparse.ArgumentParser(description="Check bioreactor batch records and analyze growth.")
    parser.add_argument("target", nargs="?", default=DEFAULT_INPUT,
                        help="a PDF or a folder of PDFs (default: data/private/raw)")
    parser.add_argument("--out", default="data/private", help="output folder (default: data/private)")
    parser.add_argument("--theme", default=DEFAULT_THEME, choices=list(THEMES),
                        help=f"report theme (default: {DEFAULT_THEME})")
    args = parser.parse_args()

    pdfs = find_pdfs(args.target)
    if not pdfs:
        raise SystemExit(f"No PDFs found in {args.target}. Add batch-record PDFs there and run again.")

    print(f"Processing {len(pdfs)} batch record(s)...\n")
    done, failed, used_ids = [], [], set()
    for pdf in pdfs:
        try:
            done.append(process(pdf, args.out, used_ids, args.theme))
            print(f"  OK      {pdf.name}")
        except Exception as error:  # one bad PDF must not stop the rest
            failed.append(pdf)
            print(f"  FAILED  {pdf.name}\n          {type(error).__name__}: {error}")

    if done:
        print("\nRun                         Critical/Major/Minor   mu_max (1/h)   Report")
        for r in done:
            print(f"{r['run']:<28}{r['findings']:<23}{r['mu_max']:<15}{r['report']}")
    print(f"\n{len(done)} report(s) written, {len(failed)} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

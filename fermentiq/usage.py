"""Anonymous usage counter for the upload app.

Stores ONLY two numbers: how many records were checked, and how many couldn't be read.
No file names, contents, results, dates or visitor details are ever saved.
"""

import json
import os
from pathlib import Path

USAGE_FILE = Path(os.environ.get("FERMENTIQ_USAGE_FILE", "data/usage.json"))


def _load():
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"records_checked": 0, "unreadable": 0}


def record(success):
    counts = _load()
    counts["records_checked" if success else "unreadable"] += 1
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(counts), encoding="utf-8")


def records_checked():
    return _load()["records_checked"]

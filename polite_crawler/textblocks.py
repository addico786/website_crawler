"""Site-wide boilerplate: text blocks (lines) found on most pages of a crawl, such as a promo
banner or a side menu that the main-text extraction kept.

The crawler finds them when it closes and writes them once to boilerplate.json; results.jsonl
is never rewritten. The dashboard strips them when it reads the results. No Scrapy import:
server.py uses this module too.
"""
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

FILE_NAME = "boilerplate.json"
SHARE = 0.5  # on at least half of the pages with text...
MIN_PAGES = 5  # ...and on at least 5 of them


def normalise(block):
    return " ".join(block.split())


def is_table_row(block):
    return block.startswith("|")


def find_boilerplate(texts):
    """(blocks, pages): the blocks found on >= 50% of the texts that have any (min 5), and how many had text.

    Table rows are never boilerplate: they are a page's data, even when many pages share a value
    (a shop's "| Tax | £0.00 |" on every product)."""
    counts = Counter()
    pages = 0
    for text in texts:
        blocks = {normalise(line) for line in (text or "").splitlines()} - {""}
        if blocks:
            pages += 1
            counts.update(block for block in blocks if not is_table_row(block))
    needed = max(MIN_PAGES, math.ceil(pages * SHARE))
    return sorted(block for block, count in counts.items() if count >= needed), pages


def write_json(path, data):
    """Write a job file in one step, so the dashboard never reads half of it."""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError:  # Windows: the dashboard is reading the old file right now
            time.sleep(0.25)
    os.replace(temp, path)


def write_boilerplate(job_dir, blocks, pages):
    write_json(Path(job_dir) / FILE_NAME, {"pages_with_text": pages, "blocks": blocks})


def load_boilerplate(job_dir):
    """The job's boilerplate blocks; an empty set when there is no usable boilerplate.json."""
    try:
        blocks = json.loads((Path(job_dir) / FILE_NAME).read_text(encoding="utf-8"))["blocks"]
        return {normalise(block) for block in blocks if isinstance(block, str)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def strip_boilerplate(text, blocks):
    if not blocks or not text:
        return text
    return "\n".join(line for line in text.splitlines() if normalise(line) not in blocks)

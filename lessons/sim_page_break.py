"""Lesson 01: simulate a paginated PDF and compare page-by-page splitting with join-then-split.

    python learn/sim_page_break.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clausecheck.parse import _normalise, _strip_repeated_lines  # noqa: E402
from clausecheck.split import split_clauses  # noqa: E402

BREAK_AFTER = "8.1 Cap on Liability"  # the page break lands right after this heading line
PAGES = 5

text = (Path(__file__).resolve().parent.parent / "data" / "sample_contract.txt").read_text(encoding="utf-8")
lines = text.splitlines()

# --- "print" the contract: 5 pages, one forced break after the target heading --------
per_page = len(lines) // PAGES
cuts = [i * per_page for i in range(1, PAGES)]
forced = lines.index(BREAK_AFTER) + 1
cuts = sorted(set(c for c in cuts if abs(c - forced) > 5) | {forced})[: PAGES - 1]
pages, start = [], 0
for n, cut in enumerate(cuts + [len(lines)], 1):
    body = "\n".join(lines[start:cut])
    pages.append(f"{body}\nCloudNotes Confidential\nPage {n} of {len(cuts) + 1}")
    start = cut

# --- A: split each page on its own, concatenate the clauses ---------------------------
a_clauses = [c for p in pages for c in split_clauses(_normalise(p))]
a_81 = next((c for c in a_clauses if c.clause_id == "8.1"), None)
a_dirty = [c for c in a_clauses if "CloudNotes Confidential" in c.text]

# --- B: drop repeated header/footer lines, join pages, then split --------------------
joined = _normalise("\n".join(_strip_repeated_lines(pages)))
b_clauses = split_clauses(joined)
b_81 = next((c for c in b_clauses if c.clause_id == "8.1"), None)


def show(label: str, clauses, c81, dirty=()):
    reviewable = [c for c in clauses if not c.is_section_title]
    print(f"\n{label}")
    print(f"  clauses found: {len(clauses)}  reviewable: {len(reviewable)}")
    if c81 is None:
        print("  8.1: NOT FOUND")
    else:
        if c81.is_section_title:
            kind = "empty -> looks like a section title, skipped by the reviewer"
        elif "Confidential" in c81.text:
            kind = "body is the PAGE FOOTER; the real text on the next page was dropped (no heading above it)"
        else:
            kind = f"ok, refs={c81.refs}"
        print(f"  8.1: {kind}")
        print(f"       text = {c81.text[:110]!r}")
    if dirty:
        print(f"  footer text leaked into: {[c.clause_id for c in dirty]}")


show("A) split page by page", a_clauses, a_81, a_dirty)
show("B) strip footers, join pages, then split (parse.py)", b_clauses, b_81)
print("\nSame contract, same model: in A the reviewer gets a page footer instead of clause 8.1, and refs=[] so it never reads Section 12.")
print("Check what went IN before touching the prompt.")

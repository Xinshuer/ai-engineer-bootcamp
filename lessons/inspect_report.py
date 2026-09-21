"""Lesson 02: list the clauses in a report that deserve a second look.

    python learn/inspect_report.py data/sample_contract.local.v2.report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAYS_FINE = re.compile(r"\b(standard|boilerplate|acceptable|consistent with|aligns with|satisf(y|ies|ying)|no never.accept)\b", re.I)

path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample_contract.local.v2.report.json")
report = json.loads(path.read_text(encoding="utf-8"))
s = report["summary"]
print(f"{report['contract_name']}  mode={report['mode']} model={report['model']}  counts={s['counts']}  errors={s['errors']}")
print(f"tokens={s['tokens']}  cache_hit={s['cache_hit_ratio']}  est_cost=${s['estimated_cost_usd']}  latency={s['total_latency_ms'] // 1000}s\n")

max_steps = max((r["trace"]["steps"] for r in report["reviews"]), default=0)
found = 0
for r in report["reviews"]:
    v, t, cid = r["verdict"], r["trace"], r["clause"]["clause_id"]
    signals = []
    if v["verdict"] != "accept" and SAYS_FINE.search(v["rationale"]):
        signals.append("rationale says it is fine but verdict is " + v["verdict"])
    if any(c.startswith("mark_for_review") for c in t["tool_calls"]):
        signals.append("called mark_for_review")
    if v["verdict"] == "redline" and not (r.get("redline") or {}).get("located"):
        signals.append("redline without a located anchor")
    if t["steps"] >= 6:
        signals.append(f"hit the step limit ({t['steps']})")
    if t.get("error"):
        signals.append("error: " + t["error"])
    if v["confidence"] == "low" and v["verdict"] != "accept" and not signals:
        signals.append("low confidence")
    if signals:
        found += 1
        print(f"[{cid}] {v['verdict']:<8} {v['topic']:<18} tools={t['tool_calls']}")
        for sig in signals:
            print(f"     - {sig}")
        print(f"     rationale: {v['rationale'][:160]}...")
print(f"\n{found} clause(s) worth a look out of {len(report['reviews'])}." if found else "\nNothing suspicious.")

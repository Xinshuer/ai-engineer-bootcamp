"""Lesson 06: watch the prompt cache hit, then break it with a timestamp.

    python learn/cache_experiment.py            # needs DEEPSEEK_API_KEY in .env
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clausecheck.config import Settings  # noqa: E402
from clausecheck.review import OpenAICompatBackend, _user_message  # noqa: E402
from clausecheck.split import load_contract  # noqa: E402

settings = Settings(mode="deepseek")
contract = load_contract("data/sample_contract.txt")
clause = contract.get("4.2")
backend = OpenAICompatBackend(settings, contract)
print(f"model={settings.model}  full_contract={settings.full_contract}  system prompt ~{len(backend.system) // 4} tokens\n")


def run(label: str, volatile_prefix: bool = False) -> None:
    print(label)
    for i in range(1, 4):
        if volatile_prefix:
            # regenerated on EVERY call, like datetime.now() in a real system prompt
            backend.system = f"Request time: {time.time()}\n\n" + original
        step = backend.step([{"role": "user", "content": _user_message(clause, contract)}])
        u = step.usage
        total = u["input"] + u["cache_read"]
        print(f"  call {i}: input={u['input']:>5}  cache_read={u['cache_read']:>5}  hit={u['cache_read'] / max(total, 1):.0%}  stop={step.stop}{'  ' + step.error if step.error else ''}")
        time.sleep(1)


run("A) stable prefix (instructions -> contract -> clause)")

original = backend.system
run("\nB) same prompt with a fresh timestamp at the START of the system prompt on every call", volatile_prefix=True)
backend.system = original

print("\nB never hits: the first byte differs on every call, so the whole prefix is new every time. Put anything that changes per request at the END.")
print("(An earlier version of this script generated the timestamp once, so B's 2nd and 3rd calls hit again. The data caught the bug.)")

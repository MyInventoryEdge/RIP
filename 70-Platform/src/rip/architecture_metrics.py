"""Low-overhead deterministic architecture counters owned by RIP."""
from __future__ import annotations
import json
from pathlib import Path

SCHEMA = "rip.architecture-metrics.v1"

def record(root: str | Path, **increments: int) -> dict[str, object]:
    path = Path(root) / "architecture-metrics.json"
    current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema": SCHEMA, "counters": {}}
    if current.get("schema") != SCHEMA: raise ValueError("architecture metrics are invalid")
    counters = dict(current["counters"])
    for name, amount in increments.items():
        if not isinstance(amount, int) or amount < 0: raise ValueError("metrics increments must be non-negative integers")
        counters[name] = int(counters.get(name, 0)) + amount
    result = {"schema": SCHEMA, "counters": dict(sorted(counters.items()))}
    temporary = path.with_suffix(".tmp"); temporary.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"); temporary.replace(path)
    return result

def read(root: str | Path) -> dict[str, object]:
    path = Path(root) / "architecture-metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema": SCHEMA, "counters": {}}

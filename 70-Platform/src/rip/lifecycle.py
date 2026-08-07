"""Single durable owner for executor-driven onboarding lifecycle transitions."""
from __future__ import annotations
import json
import os
from pathlib import Path

SCHEMA = "rip.organization-onboarding.v1"

def apply_executor_transition(*, run_directory: str | Path, expected_state: str, target_state: str, operation_id: str) -> None:
    root = Path(run_directory); path = root / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA: raise ValueError("lifecycle state is invalid")
    if state.get("state") == target_state: return
    if state.get("state") != expected_state: raise ValueError("lifecycle compare-and-swap rejected transition")
    intent = root / "lifecycle-intent.json"
    temporary = intent.with_suffix(".tmp"); temporary.write_text(json.dumps({"operation_id": operation_id, "expected_state": expected_state, "target_state": target_state}, sort_keys=True), encoding="utf-8"); os.replace(temporary, intent)
    temporary = path.with_suffix(".tmp"); temporary.write_text(json.dumps({"schema": SCHEMA, "state": target_state}, sort_keys=True), encoding="utf-8"); os.replace(temporary, path)

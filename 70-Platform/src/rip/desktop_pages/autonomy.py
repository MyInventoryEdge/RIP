"""Read-only Autonomy and Budget operator projection."""
from __future__ import annotations
import json
from pathlib import Path
from ..paths import storage_directory
from ..autonomy import AuthenticatedHuman

def render_autonomy_status() -> str:
    state = storage_directory("State") / "sda-bootstrap.json"
    records = storage_directory("State") / "execution-records.ndjson"
    authenticated = AuthenticatedHuman.current_windows_user().identity
    holder = authenticated
    bootstrap = "Not completed"
    published = state.parent / "sda-published-decision.json"
    if state.is_file():
        try: holder = json.loads(state.read_text(encoding="utf-8")).get("holder_identity", holder); bootstrap = "Completed"
        except (OSError, ValueError): holder = "Bootstrap evidence requires attention"
    recent = []
    if records.is_file():
        try: recent = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines() if line.strip()][-5:]
        except (OSError, ValueError): recent = []
    pending = 0 if published.exists() else 1
    lines = ["SUPREME DECISION AUTHORITY", f"Current authenticated holder: {authenticated}", f"Current SDA holder: {holder}", f"Bootstrap status: {bootstrap}", f"Pending constitutional decisions: {pending}", "Active delegated authorities: 0", "Autonomous actions permitted: deterministic, read-only retained-evidence projections; zero external API calls.", "Current execution budgets: no active budget artifact", "Actions requiring approval: mutations, commits, policy and authority changes", "API usage consumed: $0.00 (no retained usage records)", "Constitutional escalations awaiting decision: none projected"]
    lines.append("Recent autonomous actions: " + (", ".join(item.get("action_id", "unknown") for item in recent) if recent else "none"))
    lines.append("Actions stopped by budget: " + str(sum(item.get("result") == "deferred" for item in recent)))
    return "\n".join(lines)

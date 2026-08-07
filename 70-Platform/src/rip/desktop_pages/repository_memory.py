"""Deterministic, read-only Repository Memory projection from retained evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..paths import storage_directory


@dataclass(frozen=True, slots=True)
class RepositoryMemory:
    repository: str
    repository_root: str
    first_observation: str
    latest_observation: str
    observation_count: int
    fingerprints: tuple[str, ...]
    observed_areas: tuple[str, ...]
    capabilities: tuple[str, ...]
    runtime_areas: tuple[str, ...]
    file_count: str
    directory_count: str
    language_extensions: tuple[str, ...]
    observation_metrics: str
    growth: str
    latest_decision: str
    timeline: tuple[str, ...]


def _read(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _stage_time(run: Path) -> str:
    stages = _read(run / "stages.json", [])
    if not isinstance(stages, list): return "Not yet observed."
    times = sorted(str(item.get("operational_timestamp")) for item in stages if isinstance(item, dict) and item.get("operational_timestamp"))
    return times[0] if times else "Not yet observed."


def _capabilities(run: Path) -> tuple[str, ...]:
    evidence = (("Observation", ("initial-source-manifest.json", "final-source-manifest.json")),
                ("Governance", ("mutation-reasoning.json",)), ("Continuation", ("trust-decision-envelope.json",)),
                ("Evidence", ("integrity-difference.json",)), ("Journal", ("trust-decision-envelope.json",)))
    return tuple(name for name, required in evidence if all((run / item).is_file() for item in required)) or ("Not yet observed.",)


def _profile(workspace: Path) -> RepositoryMemory | None:
    runs = tuple(sorted((path for path in (workspace / "onboarding-runs").glob("*") if path.is_dir()), key=_stage_time)) if (workspace / "onboarding-runs").is_dir() else ()
    if not runs: return None
    latest = runs[-1]; context = _read(latest / "context.json", {})
    if not isinstance(context, dict): return None
    manifest = _read(latest / "final-source-manifest.json", {})
    difference = _read(latest / "integrity-difference.json", {})
    envelope = _read(latest / "trust-decision-envelope.json", {})
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    counts = manifest.get("counts", {}) if isinstance(manifest, dict) else {}
    top = sorted({str(item.get("path", "")).split("/", 1)[0] for item in entries if isinstance(item, dict) and item.get("path") and "/" in str(item.get("path"))})
    extensions: dict[str, int] = {}
    source_extensions = frozenset({".py", ".cs", ".js", ".ts", ".html", ".css", ".ps1", ".xaml", ".cpp", ".c", ".java", ".go", ".rs"})
    for item in entries if isinstance(entries, list) else ():
        if not isinstance(item, dict) or item.get("kind") != "file": continue
        suffix = Path(str(item.get("path", ""))).suffix.lower()
        if suffix in source_extensions: extensions[suffix] = extensions.get(suffix, 0) + 1
    runtimes = sorted({str(path).rsplit("/", 1)[0] + "/" for path in difference.get("modified_content_paths", []) if isinstance(difference, dict) and "/" in str(path)})
    observations = tuple((run, _stage_time(run), _read(run / "final-source-manifest.json", {})) for run in runs)
    fingerprints = tuple(str(data.get("aggregate_fingerprint")) for _, _, data in observations if isinstance(data, dict) and data.get("aggregate_fingerprint"))
    growth = "Not yet observed." if len(observations) < 2 else f"{len(observations)} retained observations; compare retained manifest counts."
    timeline = tuple(f"{timestamp} — {run.name}" for run, timestamp, _ in observations)
    metrics = _read(latest / "architecture-metrics.json", {})
    counters = metrics.get("counters", {}) if isinstance(metrics, dict) else {}
    metric_text = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in sorted(counters.items())) if isinstance(counters, dict) and counters else "Not yet observed."
    return RepositoryMemory(
        repository=str(context.get("organization_id", workspace.name)), repository_root=str(context.get("repository_path", "Not yet observed.")),
        first_observation=observations[0][1], latest_observation=observations[-1][1], observation_count=len(observations), fingerprints=fingerprints or ("Not yet observed.",),
        observed_areas=tuple(top) or ("Not yet observed.",), capabilities=_capabilities(latest), runtime_areas=tuple(runtimes) or ("Not yet observed.",),
        file_count=str(counts.get("file", manifest.get("entry_count", "Not yet observed."))) if isinstance(counts, dict) and isinstance(manifest, dict) else "Not yet observed.",
        directory_count=str(counts.get("directory", "Not yet observed.")) if isinstance(counts, dict) else "Not yet observed.",
        language_extensions=tuple(f"{suffix}: {count}" for suffix, count in sorted(extensions.items())) or ("Not yet observed.",), observation_metrics=metric_text, growth=growth,
        latest_decision=str(envelope.get("trust_action", "Not yet observed.")) if isinstance(envelope, dict) else "Not yet observed.", timeline=timeline or ("Not yet observed.",),
    )


def build_repository_memory() -> tuple[RepositoryMemory, ...]:
    root = storage_directory("Workspace")
    if not root.is_dir(): return ()
    return tuple(profile for workspace in sorted(path for path in root.iterdir() if path.is_dir()) if (profile := _profile(workspace)) is not None)


def render_repository_memory(memory: RepositoryMemory) -> str:
    return "\n".join((
        "Repository Memory", "", "Repository", memory.repository, "Repository root", memory.repository_root,
        f"First observation: {memory.first_observation}", f"Latest observation: {memory.latest_observation}", f"Observation count: {memory.observation_count}", f"Repository fingerprint history: {', '.join(memory.fingerprints)}", "",
        "Observed Architecture Areas", *memory.observed_areas, "", "Constitutional Capabilities", *memory.capabilities, "", "Known Runtime Areas", *memory.runtime_areas, "",
        "Repository Metrics", f"Files: {memory.file_count}", f"Directories: {memory.directory_count}", "Observed source-language extensions: " + ", ".join(memory.language_extensions), f"Retained architecture metrics: {memory.observation_metrics}", f"Growth trend: {memory.growth}", "",
        "Known Characteristics", "Observed mutable paths: " + ", ".join(memory.runtime_areas), "Protected areas: Not yet observed.", "Governed areas: " + ", ".join(memory.capabilities), "Stable architectural components: Not yet observed.", "",
        "Latest Governed Decision", memory.latest_decision, "", "Repository Timeline", *memory.timeline,
    ))

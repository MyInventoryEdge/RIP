"""Preservation, archival capture, and continuation verification boundaries.

Snapshots are created beneath the RIP-controlled organization workspace. They
never write to the customer source or alter the interrupted run.
"""

from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from ..paths import recovery_snapshot_directory

from .models import OnboardingRunState, fingerprint
from .service import (
    SOURCE_MANIFEST_SCHEMA,
    _source_manifest,
    resolve_onboarding_run_directory,
    resolve_organization_workspace,
)


RECOVERY_SNAPSHOT_SCHEMA = "rip.onboarding-recovery-snapshot.v1"
PRESERVED_RUN_SCHEMA = "rip.onboarding-preserved-run.v1"
MANIFEST_PROGRESS_INTERVAL = 200
COPY_PROGRESS_INTERVAL = 100


@dataclass(frozen=True, slots=True)
class RecoverySnapshotProgress:
    """Read-only progress emitted while RIP verifies a recovery snapshot."""

    phase: str
    processed_items: int | None = None
    total_items: int | None = None
    current_path: str | None = None


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    snapshot_id: str
    organization_id: str
    interrupted_run_id: str
    source_repository_path: str
    source_before_fingerprint: str
    source_after_fingerprint: str
    snapshot_manifest_fingerprint: str
    snapshot_path: str
    verified_stable: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PreservedInterruptedRun:
    """A sealed receipt over evidence RIP already owns; it never reads source."""
    organization_id: str
    interrupted_run_id: str
    preserved_artifacts: tuple[str, ...]
    integrity_difference_fingerprint: str | None
    artifact_inventory: tuple[dict[str, object], ...]
    fingerprint: str


def preserve_interrupted_run(*, workspace_root: str | Path, organization_id: str,
                            interrupted_run_id: str) -> PreservedInterruptedRun:
    """Seal a recoverable interrupted run using bounded RIP-owned metadata only.

    This is intentionally idempotent.  It neither traverses nor copies the
    customer source; the retained manifests and difference remain immutable.
    """
    run = resolve_onboarding_run_directory(workspace_root, organization_id, interrupted_run_id)
    context = _read_object(run / "context.json", "interrupted onboarding context")
    if context.get("organization_id") != organization_id or context.get("onboarding_run_id") != interrupted_run_id:
        raise ValueError("interrupted onboarding context does not match the selected organization and run")
    if _read_object(run / "state.json", "interrupted onboarding state").get("state") not in {OnboardingRunState.INTERRUPTED.value, OnboardingRunState.PAUSED_AFFECTED_SCOPE.value}:
        raise ValueError("only interrupted or scope-paused onboarding runs may be preserved")
    # Observation projection may be incomplete when the source changes during
    # the final integrity gate; preserve every completed artifact that exists.
    required = ("context.json", "state.json", "initial-source-manifest.json", "final-source-manifest.json", "stages.json")
    missing = tuple(name for name in required if not (run / name).is_file())
    if missing:
        raise ValueError("interrupted onboarding evidence is incomplete: " + ", ".join(missing))
    # Seal every retained artifact, not a hand-maintained convenience list.
    artifacts = tuple(sorted(str(path.relative_to(run)).replace("\\", "/") for path in run.rglob("*") if path.is_file() and path.name != "preserved-interrupted-run.json"))
    inventory = tuple({"name": name, "size": (run / name).stat().st_size,
                       "hash": hashlib.sha256((run / name).read_bytes()).hexdigest(), "identity": fingerprint({"run": interrupted_run_id, "name": name})} for name in artifacts)
    difference = _read_object(run / "integrity-difference.json", "integrity difference") if (run / "integrity-difference.json").is_file() else {}
    values = {"organization_id": organization_id, "interrupted_run_id": interrupted_run_id,
              "preserved_artifacts": artifacts, "integrity_difference_fingerprint": difference.get("difference_fingerprint"), "artifact_inventory": inventory}
    receipt = PreservedInterruptedRun(**values, fingerprint=fingerprint(values))
    path = run / "preserved-interrupted-run.json"
    if path.is_file():
        return _load_preserved_run(path)
    _write_preserved_run(path, receipt)
    return receipt


def reopen_preserved_interrupted_run(*, workspace_root: str | Path, organization_id: str,
                                    interrupted_run_id: str) -> PreservedInterruptedRun:
    """Open an existing preservation receipt without accessing customer source."""
    run = resolve_onboarding_run_directory(workspace_root, organization_id, interrupted_run_id)
    receipt = _load_preserved_run(run / "preserved-interrupted-run.json")
    if receipt.organization_id != organization_id or receipt.interrupted_run_id != interrupted_run_id:
        raise ValueError("preserved run receipt is outside the selected organization or run")
    for artifact in receipt.artifact_inventory:
        path = run / str(artifact["name"])
        if not path.is_file() or path.stat().st_size != artifact["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["hash"]:
            raise ValueError("preserved run artifact inventory no longer validates")
    return receipt


def create_archival_source_snapshot(
    *, workspace_root: str | Path, organization_id: str, interrupted_run_id: str,
    progress_callback: Callable[[RecoverySnapshotProgress], None] | None = None,
) -> RecoverySnapshot:
    """Explicitly capture an archival copy; this is never interruption recovery.

    A source manifest is measured before and after copying. If it changes,
    capture fails locally and no snapshot is represented as usable.
    """
    workspace = resolve_organization_workspace(workspace_root, organization_id)
    run = resolve_onboarding_run_directory(workspace_root, organization_id, interrupted_run_id)
    context = _read_object(run / "context.json", "interrupted onboarding context")
    if context.get("organization_id") != organization_id or context.get("onboarding_run_id") != interrupted_run_id:
        raise ValueError("interrupted onboarding context does not match the selected organization and run")
    state = _read_object(run / "state.json", "interrupted onboarding state").get("state")
    if state != OnboardingRunState.INTERRUPTED.value:
        raise ValueError("archival source snapshots require an interrupted onboarding run")
    source = Path(_required_string(context, "repository_path", "interrupted onboarding context")).resolve()
    if not source.is_dir():
        raise ValueError("interrupted onboarding source repository is unavailable")
    if workspace == source or workspace in source.parents or source in workspace.parents:
        raise ValueError("recovery snapshot workspace must remain isolated from the customer source")

    retained_manifest_path = run / "final-source-manifest.json"
    retained_manifest = _read_object(retained_manifest_path, "retained source manifest") if retained_manifest_path.is_file() else {}
    retained_entry_count = _nonnegative_int(retained_manifest.get("entry_count"))
    _report(progress_callback, "Measuring the current customer source before copying", 0, retained_entry_count)
    before = _source_manifest(
        source,
        progress=_manifest_progress(
            progress_callback,
            "Measuring the current customer source before copying",
            retained_entry_count,
        ),
    )
    snapshot_id = "snapshot-" + fingerprint({"organization_id": organization_id, "interrupted_run_id": interrupted_run_id, "source_fingerprint": before["manifest_fingerprint"]})[:24]
    destination = _recovery_root(workspace, organization_id) / snapshot_id
    source_copy = destination / "source"
    receipt = destination / "snapshot.json"
    if receipt.is_file():
        _report(progress_callback, "An existing verified recovery snapshot was found")
        return _load_snapshot(receipt)
    if destination.exists():
        raise ValueError("recovery snapshot destination already exists without a valid receipt")

    destination.mkdir(parents=True)
    file_count = _nonnegative_int(before["counts"].get("file"))
    _report(progress_callback, "Copying the verified recovery snapshot", 0, file_count)
    copied_files = 0

    def copy_file(source_path: str, destination_path: str) -> str:
        nonlocal copied_files
        result = shutil.copy2(source_path, destination_path)
        copied_files += 1
        if copied_files == 1 or copied_files % COPY_PROGRESS_INTERVAL == 0 or copied_files == file_count:
            _report(progress_callback, "Copying the verified recovery snapshot", copied_files, file_count, str(source_path))
        return result

    shutil.copytree(source, source_copy, symlinks=True, copy_function=copy_file)
    _report(progress_callback, "Rechecking the current customer source for changes", 0, int(before["entry_count"]))
    after = _source_manifest(
        source,
        progress=_manifest_progress(
            progress_callback,
            "Rechecking the current customer source for changes",
            int(before["entry_count"]),
        ),
    )
    _report(progress_callback, "Verifying the copied recovery snapshot", 0, int(before["entry_count"]))
    snapshot_manifest = _source_manifest(
        source_copy,
        progress=_manifest_progress(
            progress_callback,
            "Verifying the copied recovery snapshot",
            int(before["entry_count"]),
        ),
    )
    source_stable = before["manifest_fingerprint"] == after["manifest_fingerprint"]
    snapshot_matches_source = before["manifest_fingerprint"] == snapshot_manifest["manifest_fingerprint"]
    stable = source_stable and snapshot_matches_source
    values = {
        "snapshot_id": snapshot_id, "organization_id": organization_id,
        "interrupted_run_id": interrupted_run_id, "source_repository_path": str(source),
        "source_before_fingerprint": before["manifest_fingerprint"],
        "source_after_fingerprint": after["manifest_fingerprint"],
        "snapshot_manifest_fingerprint": snapshot_manifest["manifest_fingerprint"],
        "snapshot_path": str(source_copy), "verified_stable": stable,
    }
    snapshot = RecoverySnapshot(**values, fingerprint=fingerprint(values))
    _write_snapshot(receipt, snapshot)
    if not source_stable:
        raise ValueError("customer source changed while the recovery snapshot was captured; no usable snapshot was created")
    if not snapshot_matches_source:
        raise ValueError("recovery snapshot content does not match the verified customer source; no usable snapshot was created")
    _report(progress_callback, "Recovery snapshot verified")
    return snapshot


def load_verified_recovery_snapshot(
    *, workspace_root: str | Path, organization_id: str, snapshot_id: str,
) -> RecoverySnapshot:
    """Load and revalidate snapshot metadata without touching the customer source."""
    workspace = resolve_organization_workspace(workspace_root, organization_id)
    snapshot = _load_snapshot(_recovery_root(workspace, organization_id) / snapshot_id / "snapshot.json")
    if snapshot.organization_id != organization_id or not snapshot.verified_stable:
        raise ValueError("recovery snapshot is not valid for the selected organization")
    current = _source_manifest(Path(snapshot.snapshot_path))
    if current.get("manifest_fingerprint") != snapshot.snapshot_manifest_fingerprint:
        raise ValueError("recovery snapshot contents no longer match its immutable receipt")
    return snapshot


# Compatibility names retain the former API while making its archival nature
# visible at every promoted call site.  They must never be called by preserve.
create_verified_recovery_snapshot = create_archival_source_snapshot


def _write_preserved_run(path: Path, receipt: PreservedInterruptedRun) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"schema": PRESERVED_RUN_SCHEMA, "receipt": asdict(receipt)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _load_preserved_run(path: Path) -> PreservedInterruptedRun:
    raw = _read_object(path, "preserved interrupted run receipt")
    if raw.get("schema") != PRESERVED_RUN_SCHEMA or not isinstance(raw.get("receipt"), dict):
        raise ValueError("preserved interrupted run receipt is invalid")
    try:
        receipt = PreservedInterruptedRun(**raw["receipt"])
    except TypeError as exc:
        raise ValueError("preserved interrupted run receipt is invalid") from exc
    values = {key: value for key, value in asdict(receipt).items() if key != "fingerprint"}
    if receipt.fingerprint != fingerprint(values):
        raise ValueError("preserved interrupted run receipt fingerprint does not match")
    return receipt


def _write_snapshot(path: Path, snapshot: RecoverySnapshot) -> None:
    payload = {"schema": RECOVERY_SNAPSHOT_SCHEMA, "snapshot": asdict(snapshot)}
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _load_snapshot(path: Path) -> RecoverySnapshot:
    raw = _read_object(path, "recovery snapshot receipt")
    if raw.get("schema") != RECOVERY_SNAPSHOT_SCHEMA or not isinstance(raw.get("snapshot"), dict):
        raise ValueError("recovery snapshot receipt is invalid")
    values = raw["snapshot"]
    try:
        snapshot = RecoverySnapshot(**values)
    except TypeError as exc:
        raise ValueError("recovery snapshot receipt is invalid") from exc
    expected = {key: value for key, value in asdict(snapshot).items() if key != "fingerprint"}
    if snapshot.fingerprint != fingerprint(expected):
        raise ValueError("recovery snapshot receipt fingerprint does not match")
    return snapshot


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} is invalid")
    return value


def _required_string(value: dict[str, object], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{label} has no {key}")
    return result


def _recovery_root(workspace: Path, organization_id: str) -> Path:
    """Keep immutable snapshots outside both customer sources and run workspace."""
    return recovery_snapshot_directory(workspace, organization_id)


def _manifest_progress(
    callback: Callable[[RecoverySnapshotProgress], None] | None,
    phase: str,
    total_items: int | None,
) -> Callable[[int, str], None] | None:
    if callback is None:
        return None

    def report(processed_items: int, path: str) -> None:
        if processed_items == 1 or processed_items % MANIFEST_PROGRESS_INTERVAL == 0:
            _report(callback, phase, processed_items, total_items, path)

    return report


def _report(
    callback: Callable[[RecoverySnapshotProgress], None] | None,
    phase: str,
    processed_items: int | None = None,
    total_items: int | None = None,
    current_path: str | None = None,
) -> None:
    if callback is not None:
        callback(RecoverySnapshotProgress(phase, processed_items, total_items, current_path))


def _nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None

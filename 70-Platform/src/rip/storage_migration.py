"""Governed, resumable migration of known legacy RIP runtime storage.

Normal execution never consults legacy locations. This module is the sole
legacy reader and produces an immutable plan/receipt under governed storage.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import storage_directory, storage_root

MIGRATION_SCHEMA = "rip.storage-migration.v1"


@dataclass(frozen=True, slots=True)
class MigrationItem:
    source: str
    destination: str
    size: int
    sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class StorageMigrationPlan:
    migration_id: str
    source_roots: tuple[str, ...]
    destination_root: str
    items: tuple[MigrationItem, ...]
    conflicts: tuple[str, ...]
    artifact_count: int
    byte_count: int


@dataclass(frozen=True, slots=True)
class StorageMigrationReceipt:
    migration_id: str
    source_locations: tuple[str, ...]
    destination_root: str
    artifact_count: int
    byte_count: int
    verified_count: int
    conflicts: tuple[str, ...]
    skipped: tuple[str, ...]
    checkpoints: tuple[dict[str, object], ...]
    duration_seconds: float
    completion_state: str


def known_legacy_locations(*, current_directory: str | Path | None = None, profile_directory: str | Path | None = None) -> tuple[Path, ...]:
    """Return only known former RIP roots; this performs no mutation."""
    current = Path(current_directory or Path.cwd()).resolve()
    profile = Path(profile_directory or Path.home()).resolve()
    candidates = (current / ".rip-state", current / ".rip-voice", profile / ".rip-onboarding")
    return tuple(path for path in candidates if path.exists())


def inventory_legacy_storage(*, legacy_roots: tuple[str | Path, ...] | None = None, root: str | Path | None = None) -> StorageMigrationPlan:
    """Build a deterministic read-only plan and detect conflicts before copy."""
    destination_root = storage_root(root)
    roots = tuple(Path(item).resolve() for item in (legacy_roots if legacy_roots is not None else known_legacy_locations()))
    items: list[MigrationItem] = []; conflicts: list[str] = []
    for source_root in roots:
        if not source_root.is_dir(): continue
        for source in sorted((_contained_legacy_files(source_root)), key=lambda item: str(item).casefold()):
            relative = source.relative_to(source_root)
            destination = _destination_for(source_root.name, relative, destination_root)
            digest = _hash(source); status = "pending"
            if destination.exists():
                status = "already-verified" if destination.is_file() and destination.stat().st_size == source.stat().st_size and _hash(destination) == digest else "conflict"
                if status == "conflict": conflicts.append(str(destination))
            items.append(MigrationItem(str(source), str(destination), source.stat().st_size, digest, status))
    seed = json.dumps([(item.source, item.destination, item.sha256) for item in items], separators=(",", ":"), sort_keys=True)
    return StorageMigrationPlan("migration-" + hashlib.sha256(seed.encode()).hexdigest()[:24], tuple(str(item) for item in roots), str(destination_root), tuple(items), tuple(conflicts), len(items), sum(item.size for item in items))


def execute_storage_migration(plan: StorageMigrationPlan) -> StorageMigrationReceipt:
    """Copy a conflict-free plan, verify bytes, checkpoint after each artifact."""
    if plan.conflicts:
        raise ValueError("storage migration has destination conflicts; no files were copied")
    started = time.perf_counter(); verified = 0; skipped: list[str] = []; checkpoints: list[dict[str, object]] = []
    receipt_path = storage_directory("Diagnostics", root=plan.destination_root) / "migrations" / f"{plan.migration_id}.json"
    prior = _read_receipt(receipt_path)
    if prior and prior.completion_state == "completed": return prior
    if prior:
        checkpoints.extend(prior.checkpoints)
    for item in plan.items:
        source, destination = Path(item.source), Path(item.destination)
        _checkpoint(receipt_path, plan, checkpoints, item, "planned")
        if not source.is_file() or source.stat().st_size != item.size or _hash(source) != item.sha256:
            raise ValueError(f"storage migration source changed since planning: {source}")
        if destination.exists():
            if destination.is_file() and _hash(destination) == item.sha256:
                verified += 1; skipped.append(item.destination); _checkpoint(receipt_path, plan, checkpoints, item, "committed"); continue
            raise ValueError(f"storage migration destination changed: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        _checkpoint(receipt_path, plan, checkpoints, item, "copied")
        if destination.stat().st_size != item.size or _hash(destination) != item.sha256:
            raise RuntimeError(f"storage migration verification failed: {destination}")
        _checkpoint(receipt_path, plan, checkpoints, item, "verified")
        verified += 1; _checkpoint(receipt_path, plan, checkpoints, item, "sealed"); _checkpoint(receipt_path, plan, checkpoints, item, "committed")
    receipt = StorageMigrationReceipt(plan.migration_id, plan.source_roots, plan.destination_root, plan.artifact_count, plan.byte_count, verified, plan.conflicts, tuple(skipped), tuple(checkpoints), round(time.perf_counter() - started, 6), "completed")
    _write_receipt(receipt_path, receipt)
    return receipt


def _destination_for(legacy_name: str, relative: Path, root: Path) -> Path:
    areas = {".rip-state": "State", ".rip-voice": "Configuration", ".rip-onboarding": "Workspace"}
    if legacy_name not in areas: raise ValueError(f"unsupported legacy storage root: {legacy_name}")
    return storage_directory(areas[legacy_name], root=root) / relative


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()

def _contained_legacy_files(root: Path):
    """Legacy discovery never follows links or copies an escaped target."""
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError:
            continue
        yield path


def _read_receipt(path: Path) -> StorageMigrationReceipt | None:
    if not path.is_file(): return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != MIGRATION_SCHEMA: raise ValueError("storage migration receipt is invalid")
    values = dict(raw["receipt"])
    for name in ("source_locations", "conflicts", "skipped", "checkpoints"):
        values[name] = tuple(values[name])
    return StorageMigrationReceipt(**values)

def _checkpoint(path: Path, plan: StorageMigrationPlan, checkpoints: list[dict[str, object]], item: MigrationItem, state: str) -> None:
    record = {"source": item.source, "destination": item.destination, "sha256": item.sha256, "state": state}
    if record not in checkpoints: checkpoints.append(record)
    partial = StorageMigrationReceipt(plan.migration_id, plan.source_roots, plan.destination_root, plan.artifact_count, plan.byte_count, 0, plan.conflicts, (), tuple(checkpoints), 0.0, "in-progress")
    _write_receipt(path, partial)

def _write_receipt(path: Path, receipt: StorageMigrationReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"schema": MIGRATION_SCHEMA, "receipt": asdict(receipt)}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)

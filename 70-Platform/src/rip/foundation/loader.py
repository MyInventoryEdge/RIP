from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import ConstitutionalMemory, Foundation, FoundationArtifact, freeze_mapping
from .parser import parse_artifact
from .registry import ConstitutionalValidationError, parse_registry, validate_entries

MEMORY_SCHEMA_VERSION = "rip.constitutional-memory.v1"
BOOTSTRAP_CONSTITUTION = "RIP-000-Constitution.md"
BOOTSTRAP_REGISTRY = "RIP-007-Constitutional-Document-Registry.md"
PRIMARY_OBJECT_RE = re.compile(r"The\s+(?P<object>[A-Z][A-Za-z0-9 _-]+?)\s+SHALL\s+be\s+RIP['â€™]s\s+primary\s+object", re.IGNORECASE)


def find_foundation_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file(): current = current.parent
    for base in (current, *current.parents):
        direct = base / "00-Constitution"
        if direct.is_dir(): return direct
    raise FileNotFoundError("Could not locate 00-Constitution from the current directory or its parents.")


def default_state_path(root: Path) -> Path:
    return root.parent / "70-Platform" / ".rip-state" / "constitutional-memory.json"


def constitutional_boot(root: str | Path | None = None, *, state_path: str | Path | None = None) -> ConstitutionalMemory:
    root_path = find_foundation_root() if root is None else Path(root).expanduser().resolve()
    state = Path(state_path).expanduser().resolve() if state_path else default_state_path(root_path)
    entries, registry_hash = _bootstrap_registry(root_path)
    current_signature = _source_signature(root_path, entries)
    persisted, recovery = _read_memory(state)
    if persisted and _matches(persisted, entries, registry_hash, current_signature):
        return _memory_from_payload(persisted, root_path, "persisted")
    source = "recovered" if recovery else ("refreshed" if persisted else "rebuilt")
    memory = _build_memory(root_path, entries, registry_hash, source)
    _write_memory(state, _memory_payload(memory, _source_signature(root_path, entries)))
    return memory


def load_foundation(root: str | Path | None = None, *, state_path: str | Path | None = None) -> Foundation:
    return constitutional_boot(root, state_path=state_path)


def _bootstrap_registry(root: Path):
    for filename in (BOOTSTRAP_CONSTITUTION, BOOTSTRAP_REGISTRY):
        if not (root / filename).is_file():
            raise FileNotFoundError(f"Required constitutional bootstrap artifact is missing: {filename}")
    entries = validate_entries(parse_registry(root / BOOTSTRAP_REGISTRY))
    return entries, _hash_file(root / BOOTSTRAP_REGISTRY)


def _build_memory(root: Path, entries, registry_hash: str, source: str) -> ConstitutionalMemory:
    artifacts: list[FoundationArtifact] = []
    hashes: dict[str, str] = {}
    for entry in entries:
        path = root / entry.filename
        if not path.is_file(): raise FileNotFoundError(f"Registered constitutional artifact is missing: {entry.filename}")
        artifact = parse_artifact(path)
        if artifact.artifact_id != entry.document_id or artifact.title != entry.title:
            raise ConstitutionalValidationError(f"Registry identity does not match {entry.filename}")
        if artifact.metadata.get("Version") != entry.version:
            raise ConstitutionalValidationError(f"Registry version does not match {entry.filename}")
        artifacts.append(artifact); hashes[entry.document_id] = _hash_content(artifact.raw_markdown)
    lexicon = {section.heading.strip(): section.body.strip() for section in next(item for item in artifacts if item.artifact_id == "RIP-002").sections if section.body.strip()}
    fingerprint = _fingerprint(entries, registry_hash, hashes)
    return ConstitutionalMemory(root, tuple(artifacts), entries, freeze_mapping(hashes), registry_hash, fingerprint, MEMORY_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat(), source, freeze_mapping(lexicon), _extract_primary_object(next(item for item in artifacts if item.artifact_id == "RIP-000")))


def _extract_primary_object(constitution: FoundationArtifact) -> str:
    match = PRIMARY_OBJECT_RE.search(constitution.section("Primary Object").body)
    if not match: raise ConstitutionalValidationError("Could not determine RIP's primary object from the Constitution")
    return match.group("object").strip().title()


def _source_signature(root: Path, entries) -> dict[str, dict[str, int]]:
    return {entry.filename: {"size": (stat := (root / entry.filename).stat()).st_size, "mtime_ns": stat.st_mtime_ns} for entry in entries}


def _matches(payload, entries, registry_hash, signature) -> bool:
    return payload.get("schema_version") == MEMORY_SCHEMA_VERSION and payload.get("registry_hash") == registry_hash and payload.get("entries") == [_entry_payload(item) for item in entries] and payload.get("source_signature") == signature and _payload_hashes_valid(payload)


def _payload_hashes_valid(payload) -> bool:
    return all(hashlib.sha256(item["content"].encode("utf-8")).hexdigest() == item["content_hash"] for item in payload.get("documents", []))


def _memory_payload(memory: ConstitutionalMemory, signature) -> dict:
    return {"schema_version": memory.memory_schema_version, "registry_hash": memory.registry_hash, "corpus_fingerprint": memory.corpus_fingerprint, "validated_at": memory.validation_timestamp, "entries": [_entry_payload(item) for item in memory.registry_entries], "source_signature": signature, "documents": [{"id": item.artifact_id, "title": item.title, "filename": item.path.name, "version": item.metadata.get("Version"), "content_hash": memory.document_hashes[item.artifact_id], "content": item.raw_markdown} for item in memory.artifacts]}


def _memory_from_payload(payload, root: Path, source: str) -> ConstitutionalMemory:
    documents = []
    for item in payload["documents"]:
        path = root / item["filename"]
        documents.append(parse_artifact_from_memory(item, path))
    entries = tuple(_entry_from_payload(item) for item in payload["entries"])
    lexicon = {section.heading.strip(): section.body.strip() for section in next(item for item in documents if item.artifact_id == "RIP-002").sections if section.body.strip()}
    hashes = {item["id"]: item["content_hash"] for item in payload["documents"]}
    return ConstitutionalMemory(root, tuple(documents), entries, freeze_mapping(hashes), payload["registry_hash"], payload["corpus_fingerprint"], payload["schema_version"], payload["validated_at"], source, freeze_mapping(lexicon), _extract_primary_object(next(item for item in documents if item.artifact_id == "RIP-000")))


def parse_artifact_from_memory(item: dict, path: Path) -> FoundationArtifact:
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as temp:
        temp.write(item["content"]); temp_path = Path(temp.name)
    try:
        parsed = parse_artifact(temp_path)
        return FoundationArtifact(parsed.artifact_id, parsed.title, path, parsed.metadata, parsed.sections, parsed.raw_markdown)
    finally: temp_path.unlink(missing_ok=True)


def _read_memory(path: Path):
    if not path.is_file(): return None, False
    try:
        return json.loads(path.read_text(encoding="utf-8")), False
    except (OSError, json.JSONDecodeError, KeyError, TypeError): return None, True


def _write_memory(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8")); temporary.replace(path)


def _hash_file(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _hash_content(content: str) -> str: return hashlib.sha256(content.encode("utf-8")).hexdigest()
def _fingerprint(entries, registry_hash, hashes): return hashlib.sha256(json.dumps({"registry": registry_hash, "entries": [_entry_payload(item) for item in entries], "hashes": hashes}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _entry_payload(item): return {"sequence": item.sequence, "document_id": item.document_id, "title": item.title, "filename": item.filename, "version": item.version, "status": item.status}
def _entry_from_payload(item): return __import__("rip.foundation.models", fromlist=["RegistryEntry"]).RegistryEntry(item["sequence"], item["document_id"], item["title"], item["filename"], item["version"], item["status"], freeze_mapping({}))

from __future__ import annotations

import re
from pathlib import Path

from .models import RegistryEntry, freeze_mapping


class ConstitutionalValidationError(ValueError):
    pass


def parse_registry(path: Path) -> tuple[RegistryEntry, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "Document ID" not in line or "Filename" not in line or "Sequence" not in line:
            continue
        headers = _cells(line)
        if index + 1 >= len(lines) or not _is_separator(lines[index + 1]):
            continue
        entries: list[RegistryEntry] = []
        for row in lines[index + 2 :]:
            if not row.strip().startswith("|"):
                break
            values = _cells(row)
            if len(values) != len(headers):
                raise ConstitutionalValidationError("Registry row does not match its header width")
            fields = dict(zip(headers, values, strict=True))
            try:
                sequence = int(fields["Sequence"])
            except ValueError as exc:
                raise ConstitutionalValidationError(f"Invalid registry sequence: {fields.get('Sequence')!r}") from exc
            entries.append(RegistryEntry(
                sequence=sequence,
                document_id=fields["Document ID"],
                title=fields["Title"],
                filename=fields["Filename"],
                version=fields["Version"],
                status=fields["Status"],
                fields=freeze_mapping(fields),
            ))
        if entries:
            return tuple(entries)
    raise ConstitutionalValidationError("RIP-007 has no registry table with Sequence and Filename columns")


def validate_entries(entries: tuple[RegistryEntry, ...]) -> tuple[RegistryEntry, ...]:
    active = tuple(sorted((entry for entry in entries if entry.active), key=lambda item: item.sequence))
    if not active:
        raise ConstitutionalValidationError("Registry contains no active constitutional artifacts")
    for required in ("RIP-000", "RIP-007"):
        if required not in {entry.document_id for entry in active}:
            raise ConstitutionalValidationError(f"Registry is missing required active artifact: {required}")
    for label, values in (("identifier", [item.document_id for item in active]), ("filename", [item.filename for item in active]), ("sequence", [item.sequence for item in active])):
        if len(values) != len(set(values)):
            raise ConstitutionalValidationError(f"Registry has duplicate active {label}s")
    if any(item.sequence < 0 for item in active):
        raise ConstitutionalValidationError("Registry sequences must be non-negative")
    if [item.sequence for item in active] != list(range(len(active))):
        raise ConstitutionalValidationError("Active registry sequences must be contiguous starting at zero")
    if any(not re.fullmatch(r"RIP-\d{3}", item.document_id) for item in active):
        raise ConstitutionalValidationError("Registry has an invalid document identifier")
    if any(Path(item.filename).name != item.filename or not item.filename.endswith(".md") for item in active):
        raise ConstitutionalValidationError("Registry has an invalid constitutional filename")
    return active


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in _cells(line))

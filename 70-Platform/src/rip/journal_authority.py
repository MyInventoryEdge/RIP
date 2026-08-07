"""Domain-agnostic authenticated publication ledger and committed-head authority."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from .platform_keys import AUTHORITY_ID, sign, verify
from .producer_policy import ProducerPolicyAuthority
from .journal_mutex import journal_authority_lock
from .journal_storage import PlatformJournalStorage

RECORD_SCHEMA = "rip.journal-record.v3"
HEAD_SCHEMA = "rip.journal-head.v2"
REGISTRY_SCHEMA = "rip.journal-producer-registry.v1"
DISPOSITION_SCHEMA = "rip.publication-disposition.v1"
ZERO_HASH = "0" * 64


def _canon(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
def _hash(value): return hashlib.sha256(_canon(value)).hexdigest()
def _sign(signer, payload): return signer.sign(_canon(payload))
def _verify(signer, payload, binding): return signer.verify(_canon(payload), binding)
def _load(path): return json.loads(path.read_text())
def _lines(path): return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
def _seam(seams, name):
    if seams is not None: seams(name)


class _Signer:
    def sign(self, payload): return sign(payload)
    def verify(self, payload, binding): return verify(payload, binding)


class JournalAuthority:
    """Injected façade for the sole authenticated publication authority."""
    def __init__(self, *, key_provider, policy_authority, storage):
        self._key_provider = key_provider
        self._policy_authority = policy_authority
        self._storage = storage

    def publish(self, **kwargs):
        return publish(signer=self._key_provider, policy_authority=self._policy_authority,
                       storage=self._storage, **kwargs)

    def validate(self):
        return validate(signer=self._key_provider, policy_authority=self._policy_authority,
                        storage=self._storage)


def _append(path, value, seams=None, phase="record"):
    path.parent.mkdir(parents=True, exist_ok=True)
    _seam(seams, "before temporary " + phase + " creation")
    if phase == "record":
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())
        _seam(seams, "after final record publication")
        return
    _seam(seams, "after temporary " + phase + " creation")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())
    _seam(seams, "after " + phase + " flush")
    _seam(seams, "after final " + phase + " publication")


def _atomic(path, value, seams=None):
    temporary = path.with_suffix(".tmp"); path.parent.mkdir(parents=True, exist_ok=True)
    _seam(seams, "before temporary head creation")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True)); handle.flush(); os.fsync(handle.fileno())
    _seam(seams, "after temporary head creation"); _seam(seams, "after head flush")
    os.replace(temporary, path); _seam(seams, "after head replacement")


def _pending(storage, record, seams):
    path = storage.pending_directory() / (record["record_hash"] + ".record"); path.parent.mkdir(parents=True, exist_ok=True)
    _seam(seams, "before temporary record creation")
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True)); handle.flush(); os.fsync(handle.fileno())
    _seam(seams, "after temporary record creation"); _seam(seams, "after record flush")
    return path


def _admit(certificate, policy_authority, authority_type, authority_id, record_type):
    """Bind publication to immutable, historically resolvable policy evidence."""
    if certificate is None:
        raise ValueError("Producer Admission Certificate is required")
    authority = policy_authority or ProducerPolicyAuthority()
    resolved = authority.resolve_admission_certificate(certificate.get("certificate_id"))
    if resolved != certificate:
        raise ValueError("admission certificate substitution")
    authority.validate_admission_certificate(
        certificate, producer_authority_type=authority_type,
        producer_authority_id=authority_id, producer_record_type=record_type)
    return certificate


def _verify_disposition(signer, disposition):
    body = disposition.copy(); signature = body.pop("signature", None)
    return body.get("schema") == DISPOSITION_SCHEMA and _verify(signer, body, signature)


def _state(*, signer, storage):
    records = _lines(storage.journal_path()); heads = _lines(storage.head_history_path())
    dispositions = _lines(storage.quarantine_directory() / "dispositions.ndjson")
    return records, heads, dispositions


def validate(*, signer=None, storage=None, policy_authority=None):
    """Validate immutable ledger evidence and independently committed Head History."""
    signer = signer or _Signer(); storage = storage or PlatformJournalStorage()
    records, heads, dispositions = _state(signer=signer, storage=storage)
    policy = policy_authority or getattr(storage, "_policy_authority", None) or ProducerPolicyAuthority()
    # A derived index is valid only for this validation call.  It follows a
    # complete policy-history validation and is discarded on return; it never
    # becomes an authority cache.
    certificates = policy.validated_admission_snapshot()
    previous_record = ZERO_HASH
    record_by_hash = {}
    for sequence, record in enumerate(records, 1):
        body = record.copy(); signature = body.pop("signature", None); record_hash = body.pop("record_hash", None)
        if (record.get("schema") != RECORD_SCHEMA or record.get("publication_sequence") != sequence or
                record.get("previous_record_hash") != previous_record or
                record.get("canonical_payload_hash") != _hash(record.get("canonical_payload")) or
                record_hash != _hash(body) or not _verify(signer, {key: value for key, value in record.items() if key != "signature"}, signature)):
            raise ValueError("invalid publication ledger record")
        certificate = certificates.get(record.get("admission_certificate_id"))
        if certificate is None:
            raise ValueError("publication certificate is absent from validated policy history")
        if (certificate.get("integrity_hash") != record.get("admission_certificate_integrity_hash") or
                certificate.get("policy_root_hash") != record.get("admission_policy_root_hash")):
            raise ValueError("publication admission binding mismatch")
        policy.validate_admission_certificate(certificate, producer_authority_type=record["producer_authority_type"],
                                              producer_authority_id=record["producer_authority_id"],
                                              producer_record_type=record["producer_record_type"], at=record["published_at"])
        if record_hash in record_by_hash: raise ValueError("duplicate publication identity")
        record_by_hash[record_hash] = record; previous_record = record_hash
    previous_head = ZERO_HASH; committed_hashes = set(); previous_publication = 0
    for sequence, head in enumerate(heads, 1):
        body = head.copy(); signature = body.pop("signature", None); head_hash = body.pop("head_hash", None)
        record = record_by_hash.get(head.get("record_hash"))
        if (head.get("schema") != HEAD_SCHEMA or head.get("commit_sequence") != sequence or
                head.get("referenced_publication_sequence") is None or
                head["referenced_publication_sequence"] <= previous_publication or
                record is None or record.get("publication_sequence") != head["referenced_publication_sequence"] or
                head.get("previous_head_hash") != previous_head or head_hash != _hash(body) or
                not _verify(signer, {key: value for key, value in head.items() if key != "signature"}, signature)):
            raise ValueError("invalid authenticated head history")
        if head["record_hash"] in committed_hashes: raise ValueError("duplicate committed publication")
        committed_hashes.add(head["record_hash"]); previous_head = head_hash; previous_publication = head["referenced_publication_sequence"]
    disposed = set()
    for disposition in dispositions:
        if not _verify_disposition(signer, disposition): raise ValueError("invalid publication disposition")
        record_hash = disposition.get("record_hash")
        if record_hash not in record_by_hash or record_hash in committed_hashes or record_hash in disposed:
            raise ValueError("invalid publication disposition binding")
        if disposition.get("publication_sequence") != record_by_hash[record_hash]["publication_sequence"]:
            raise ValueError("invalid disposition sequence binding")
        disposed.add(record_hash)
    unreferenced = set(record_by_hash) - committed_hashes
    if unreferenced != disposed: raise ValueError("uncommitted publication lacks immutable disposition")
    if storage.head_path().exists() and heads:
        try: projection = _load(storage.head_path())
        except Exception as error: raise ValueError("invalid current head projection") from error
        # The projection is non-authoritative and can lag an already committed
        # head after a crash; it must nevertheless name authenticated history.
        if projection not in heads: raise ValueError("current head projection replacement")
    return heads[-1] if heads else {}


def publish(*, producer_authority_type, producer_authority_id, producer_record_type, producer_record_id,
            canonical_payload, producer_admission_certificate=None, policy_authority=None,
            signer=None, storage=None, _test_seam=None):
    signer = signer or _Signer(); storage = storage or PlatformJournalStorage()
    with journal_authority_lock():
        certificate = _admit(producer_admission_certificate, policy_authority, producer_authority_type,
                             producer_authority_id, producer_record_type)
        head = validate(signer=signer, storage=storage, policy_authority=policy_authority)
        records, _, _ = _state(signer=signer, storage=storage)
        publication_sequence = len(records) + 1
        commit_sequence = head.get("commit_sequence", 0) + 1
        previous_record = records[-1]["record_hash"] if records else ZERO_HASH
        record = {
            "schema": RECORD_SCHEMA, "publication_sequence": publication_sequence,
            "producer_authority_type": producer_authority_type, "producer_authority_id": producer_authority_id,
            "producer_record_type": producer_record_type, "producer_record_id": producer_record_id,
            "admission_certificate_id": certificate["certificate_id"],
            "admission_certificate_integrity_hash": certificate["integrity_hash"],
            "admission_policy_root_hash": certificate["policy_root_hash"],
            "canonical_payload": canonical_payload, "canonical_payload_hash": _hash(canonical_payload),
            "previous_record_hash": previous_record, "published_at": datetime.now(timezone.utc).isoformat(),
            "signing_authority_id": AUTHORITY_ID, "signing_key_id": "active", "signature_version": 1,
        }
        record["record_hash"] = _hash(record); record["signature"] = _sign(signer, record)
        pending = _pending(storage, record, _test_seam); _append(storage.journal_path(), record, _test_seam, "record")
        head = {
            "schema": HEAD_SCHEMA, "commit_sequence": commit_sequence,
            "referenced_publication_sequence": publication_sequence, "record_hash": record["record_hash"],
            "previous_head_hash": head.get("head_hash", ZERO_HASH), "published_at": record["published_at"],
            "signing_authority_id": AUTHORITY_ID, "signing_key_id": "active", "signature_version": 1,
        }
        head["head_hash"] = _hash(head); head["signature"] = _sign(signer, head)
        _append(storage.head_history_path(), head, _test_seam, "head history")
        _seam(_test_seam, "after authenticated head-history publication"); _atomic(storage.head_path(), head, _test_seam)
        _seam(_test_seam, "before final publication verification"); pending.unlink(missing_ok=True)
        return record


def disposition_publication(*, record_hash, disposition, reason, signer=None, storage=None):
    """Append signed disposition evidence; committed history is never rewritten."""
    if disposition not in {"quarantined", "abandoned", "superseded", "retired"}: raise ValueError("invalid disposition")
    signer = signer or _Signer(); storage = storage or PlatformJournalStorage()
    records, heads, existing = _state(signer=signer, storage=storage)
    record = next((item for item in records if item.get("record_hash") == record_hash), None)
    if record is None or any(head.get("record_hash") == record_hash for head in heads): raise ValueError("invalid disposition target")
    if any(item.get("record_hash") == record_hash for item in existing): raise ValueError("publication already dispositioned")
    body = {"schema": DISPOSITION_SCHEMA, "record_hash": record_hash,
            "publication_sequence": record["publication_sequence"], "disposition": disposition, "reason": reason,
            "published_at": datetime.now(timezone.utc).isoformat(), "signing_authority_id": AUTHORITY_ID}
    body["signature"] = _sign(signer, body)
    _append(storage.quarantine_directory() / "dispositions.ndjson", body)
    return body

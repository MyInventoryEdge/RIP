"""Producer Policy Authority: immutable admission-policy evidence only."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
import inspect
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone

from .platform_keys import AUTHORITY_ID, sign, verify
from .producer_policy_storage import PlatformProducerPolicyStorage
from .paths import storage_directory

POLICY_AUTHORITY_ID = "rip-producer-policy-authority"
POLICY_SCHEMA = "rip.producer-policy-revision.v1"
CERTIFICATE_SCHEMA = "rip.producer-admission-certificate.v1"
EVENT_SCHEMAS = {
    "retire": "rip.producer-retirement-event.v1",
    "revoke": "rip.producer-revocation-event.v1",
    "compromise": "rip.producer-compromise-event.v1",
    "key_rotation": "rip.producer-key-rotation-authorization.v1",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class _PlatformSigner:
    def sign(self, payload):
        return sign(payload)

    def verify(self, payload, binding):
        return verify(payload, binding)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_lines(path):
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("invalid immutable policy evidence") from error


def _append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_projection(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _binding(signer, body):
    body["integrity_hash"] = _hash(body)
    body["signature"] = signer.sign(_canonical(body))
    return body


def _verify_bound(signer, artifact, schema):
    if not isinstance(artifact, Mapping) or artifact.get("schema") != schema:
        diagnostic = {
            "schema": "rip.policy-evidence-schema-rejection.v1",
            "expected_schema": schema,
            "artifact_schema": artifact.get("schema") if isinstance(artifact, Mapping) else None,
            "artifact_type": type(artifact).__name__,
            "artifact_identifier": next((artifact.get(key) for key in ("certificate_id", "event_id", "policy_root_hash", "revision_sequence") if isinstance(artifact, Mapping) and artifact.get(key) is not None), None),
            "caller": inspect.stack()[1].function,
            "traceback": traceback.format_stack(),
            "captured_at": _now(),
        }
        directory = storage_directory("Diagnostics")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("policy-evidence-schema-rejection-" + uuid.uuid4().hex + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(diagnostic, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
        raise ValueError("unsupported policy evidence schema")
    body = dict(artifact)
    signature = body.pop("signature", None)
    integrity = body.pop("integrity_hash", None)
    if not isinstance(signature, dict) or integrity != _hash(body):
        raise ValueError("invalid policy evidence integrity")
    if not signer.verify(_canonical({**body, "integrity_hash": integrity}), signature):
        raise ValueError("invalid policy evidence signature")
    if artifact.get("policy_authority_id") != POLICY_AUTHORITY_ID:
        raise ValueError("wrong policy authority")


def _identity(authority_type, authority_id):
    if not authority_type or not authority_id:
        raise ValueError("producer identity is required")
    return authority_type, authority_id


class ProducerPolicyAuthority:
    """The sole owner of immutable producer-admission policy evidence."""

    def __init__(self, *, signer=None, storage=None):
        self._signer = signer or _PlatformSigner()
        self._storage = storage or PlatformProducerPolicyStorage()

    def propose_producer_admission(self, *, producer_authority_type, producer_authority_id,
                                   permitted_record_types, producer_key_reference,
                                   effective_from=None, effective_until=None):
        _identity(producer_authority_type, producer_authority_id)
        if not permitted_record_types or not all(isinstance(item, str) and item for item in permitted_record_types):
            raise ValueError("permitted record types are required")
        return {
            "producer_authority_type": producer_authority_type,
            "producer_authority_id": producer_authority_id,
            "permitted_record_types": tuple(sorted(set(permitted_record_types))),
            "producer_key_reference": producer_key_reference,
            "effective_from": effective_from or _now(),
            "effective_until": effective_until,
        }

    def admit_producer(self, **proposal):
        return self.issue_admission_certificate(**proposal)

    def issue_admission_certificate(self, *, producer_authority_type, producer_authority_id,
                                    permitted_record_types, producer_key_reference,
                                    effective_from=None, effective_until=None):
        proposal = self.propose_producer_admission(
            producer_authority_type=producer_authority_type,
            producer_authority_id=producer_authority_id,
            permitted_record_types=permitted_record_types,
            producer_key_reference=producer_key_reference,
            effective_from=effective_from,
            effective_until=effective_until,
        )
        previous = self.validate_policy_history()
        sequence = previous["revision_sequence"] + 1 if previous else 1
        previous_root = previous["policy_root_hash"] if previous else "0" * 64
        certificate = _binding(self._signer, {
            "schema": CERTIFICATE_SCHEMA, "version": 1,
            "certificate_id": "pac-" + uuid.uuid4().hex,
            "policy_authority_id": POLICY_AUTHORITY_ID,
            "producer_authority_type": proposal["producer_authority_type"],
            "producer_authority_id": proposal["producer_authority_id"],
            "permitted_record_types": list(proposal["permitted_record_types"]),
            "producer_key_reference": proposal["producer_key_reference"],
            "policy_revision_sequence": sequence,
            "policy_root_hash": None,
            "effective_from": proposal["effective_from"],
            "effective_until": proposal["effective_until"],
            "admission_status_at_issuance": "active",
            "issued_at": _now(), "signing_authority_id": AUTHORITY_ID,
            "signing_key_id": "active", "signature_version": 1,
        })
        root = self._policy_root(sequence, previous_root, [certificate], [])
        certificate["policy_root_hash"] = root
        certificate.pop("integrity_hash"); certificate.pop("signature")
        _binding(self._signer, certificate)
        _append(self._storage.certificate_path(), certificate)
        self._append_revision(sequence, previous_root, root, [certificate], [])
        return certificate

    def change_permitted_record_types(self, *, producer_authority_type, producer_authority_id,
                                      permitted_record_types, producer_key_reference,
                                      effective_from=None, effective_until=None):
        return self.issue_admission_certificate(
            producer_authority_type=producer_authority_type, producer_authority_id=producer_authority_id,
            permitted_record_types=permitted_record_types, producer_key_reference=producer_key_reference,
            effective_from=effective_from, effective_until=effective_until)

    def authorize_producer_key_rotation(self, *, producer_authority_type, producer_authority_id,
                                        previous_key_reference, producer_key_reference, effective_from=None):
        return self._event("key_rotation", producer_authority_type, producer_authority_id,
                           {"previous_key_reference": previous_key_reference,
                            "producer_key_reference": producer_key_reference}, effective_from)

    def retire_producer(self, *, producer_authority_type, producer_authority_id, reason, effective_from=None):
        return self._event("retire", producer_authority_type, producer_authority_id, {"reason": reason}, effective_from)

    def revoke_producer(self, *, producer_authority_type, producer_authority_id, reason, effective_from=None):
        return self._event("revoke", producer_authority_type, producer_authority_id, {"reason": reason}, effective_from)

    def declare_producer_compromise(self, *, producer_authority_type, producer_authority_id, reason, effective_from=None):
        # Records evidence only. Historical reclassification has no owner in this V1.
        return self._event("compromise", producer_authority_type, producer_authority_id, {"reason": reason}, effective_from)

    def _event(self, kind, authority_type, authority_id, detail, effective_from):
        _identity(authority_type, authority_id)
        prior = self.validate_policy_history()
        sequence = prior["revision_sequence"] + 1 if prior else 1
        predecessor = prior["policy_root_hash"] if prior else "0" * 64
        event = _binding(self._signer, {
            "schema": EVENT_SCHEMAS[kind], "version": 1, "event_id": "ppe-" + uuid.uuid4().hex,
            "policy_authority_id": POLICY_AUTHORITY_ID, "producer_authority_type": authority_type,
            "producer_authority_id": authority_id, "effective_from": effective_from or _now(),
            "issued_at": _now(), "signing_authority_id": AUTHORITY_ID,
            "signing_key_id": "active", "signature_version": 1, **detail,
        })
        root = self._policy_root(sequence, predecessor, [], [event])
        _append(self._storage.event_path(), event)
        self._append_revision(sequence, predecessor, root, [], [event])
        return event

    def _policy_root(self, sequence, previous_root, certificates, events):
        return _hash({"policy_authority_id": POLICY_AUTHORITY_ID, "revision_sequence": sequence,
                      "previous_policy_root_hash": previous_root,
                      # A certificate binds this root, so including its integrity hash here
                      # would be circular. The signed revision binds certificate hashes.
                      "certificate_ids": [c["certificate_id"] for c in certificates],
                      "event_ids": [e["event_id"] for e in events]})

    def _append_revision(self, sequence, predecessor, root, certificates, events):
        revision = _binding(self._signer, {
            "schema": POLICY_SCHEMA, "version": 1, "policy_authority_id": POLICY_AUTHORITY_ID,
            "revision_sequence": sequence, "previous_policy_root_hash": predecessor,
            "policy_root_hash": root, "effective_from": _now(),
            "certificate_references": [{"certificate_id": c["certificate_id"], "integrity_hash": c["integrity_hash"]} for c in certificates],
            "event_references": [{"event_id": e["event_id"], "integrity_hash": e["integrity_hash"]} for e in events],
            "issued_at": _now(), "signing_authority_id": AUTHORITY_ID, "signing_key_id": "active", "signature_version": 1,
        })
        _append(self._storage.policy_history_path(), revision)
        _atomic_projection(self._storage.current_policy_path(), revision)
        return revision

    def resolve_admission_certificate(self, certificate_id):
        certificates = self.validated_admission_snapshot()
        certificate = certificates.get(certificate_id)
        if certificate is None:
            raise ValueError("certificate is not immutable policy history")
        self.validate_admission_certificate(certificate)
        return certificate

    def validated_admission_snapshot(self):
        """Return a call-scoped, derived certificate index after full validation.

        The caller must discard this value after its one validation operation.
        It is not a cache and cannot replace a fresh policy-history validation.
        """
        self.validate_policy_history()
        certificates = {item["certificate_id"]: item for item in _read_lines(self._storage.certificate_path())}
        referenced = {ref["certificate_id"]: ref["integrity_hash"] for revision in _read_lines(self._storage.policy_history_path()) for ref in revision["certificate_references"]}
        for certificate_id, certificate in tuple(certificates.items()):
            if referenced.get(certificate_id) != certificate.get("integrity_hash"):
                certificates.pop(certificate_id)
        return certificates

    def validate_admission_certificate(self, certificate, *, producer_authority_type=None,
                                       producer_authority_id=None, producer_record_type=None, at=None):
        _verify_bound(self._signer, certificate, CERTIFICATE_SCHEMA)
        if certificate.get("version") != 1 or not certificate.get("certificate_id"):
            raise ValueError("invalid certificate")
        if producer_authority_type and certificate.get("producer_authority_type") != producer_authority_type:
            raise ValueError("wrong producer identity")
        if producer_authority_id and certificate.get("producer_authority_id") != producer_authority_id:
            raise ValueError("wrong producer identity")
        if producer_record_type and producer_record_type not in certificate.get("permitted_record_types", []):
            raise ValueError("unauthorized record type")
        moment = at or _now()
        if certificate.get("effective_from", "") > moment or (certificate.get("effective_until") and moment > certificate["effective_until"]):
            raise ValueError("stale certificate")
        return True

    def validate_policy_history(self):
        revisions = _read_lines(self._storage.policy_history_path())
        certificate_rows = _read_lines(self._storage.certificate_path())
        event_rows = _read_lines(self._storage.event_path())
        if len({item.get("certificate_id") for item in certificate_rows}) != len(certificate_rows):
            raise ValueError("duplicate certificate")
        if len({item.get("event_id") for item in event_rows}) != len(event_rows):
            raise ValueError("duplicate policy event")
        certificates = {item.get("certificate_id"): item for item in certificate_rows}
        events = {item.get("event_id"): item for item in event_rows}
        predecessor = "0" * 64
        for sequence, revision in enumerate(revisions, 1):
            _verify_bound(self._signer, revision, POLICY_SCHEMA)
            if revision.get("version") != 1 or revision.get("revision_sequence") != sequence or revision.get("previous_policy_root_hash") != predecessor:
                raise ValueError("invalid policy revision sequence")
            certs = []
            for ref in revision.get("certificate_references", []):
                certificate = certificates.get(ref.get("certificate_id"))
                if certificate is None or certificate.get("integrity_hash") != ref.get("integrity_hash"):
                    raise ValueError("missing certificate binding")
                _verify_bound(self._signer, certificate, CERTIFICATE_SCHEMA); certs.append(certificate)
                if certificate.get("policy_revision_sequence") != sequence or certificate.get("policy_root_hash") != revision.get("policy_root_hash"):
                    raise ValueError("invalid certificate policy binding")
            linked_events = []
            for ref in revision.get("event_references", []):
                event = events.get(ref.get("event_id"))
                if event is None or event.get("integrity_hash") != ref.get("integrity_hash") or event.get("schema") not in EVENT_SCHEMAS.values():
                    raise ValueError("missing event binding")
                _verify_bound(self._signer, event, event["schema"]); linked_events.append(event)
            if revision.get("policy_root_hash") != self._policy_root(sequence, predecessor, certs, linked_events):
                raise ValueError("invalid policy root hash")
            predecessor = revision["policy_root_hash"]
        projection = self._storage.current_policy_path()
        if revisions:
            if not projection.exists():
                raise ValueError("missing current policy projection")
            try:
                current = json.loads(projection.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError("invalid current policy projection") from error
            if current != revisions[-1]:
                raise ValueError("policy history truncation or replacement")
        elif projection.exists():
            raise ValueError("unexpected current policy projection")
        return revisions[-1] if revisions else {}

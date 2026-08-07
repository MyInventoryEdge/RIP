from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from rip.mutation import interpret_mutation
from rip.trust_actions import execute_persisted_continuation as _continue, execute_trust_action as _execute, verify_declared_scope, _fingerprint
from rip.producer_policy import ProducerPolicyAuthority
from rip.journal_authority import JournalAuthority
from tests.journal_test_storage import TemporaryJournalStorage
from tests.journal_test_signer import DeterministicTestSignatureProvider
from rip.architecture_metrics import record, read
from rip.paths import storage_root
from rip.onboarding.service import _source_manifest

_contexts={}
def _context(run):
 key=str(Path(run).parent);ctx=_contexts.get(key)
 if ctx:return ctx
 storage=TemporaryJournalStorage(Path(key)/"journal"); signer=DeterministicTestSignatureProvider(); policy=ProducerPolicyAuthority(signer=signer,storage=storage); certificate=policy.admit_producer(producer_authority_type="trust-authority",producer_authority_id="trust-v1",permitted_record_types=("trust-decision-envelope",),producer_key_reference="test")
 ctx={"platform_key_provider":signer,"producer_policy_authority":policy,"producer_admission_certificate":certificate,"journal_authority":JournalAuthority(key_provider=signer,policy_authority=policy,storage=storage),"journal_storage":storage};_contexts[key]=ctx;return ctx
def execute_trust_action(**kwargs):kwargs["journal_context"]=_context(kwargs["run_directory"]);return _execute(**kwargs)
def execute_persisted_continuation(**kwargs):kwargs["journal_context"]=_context(kwargs["run_directory"]);return _continue(**kwargs)


class ArchitecturalObligationTests(unittest.TestCase):
    def test_scope_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"; root.mkdir()
            with self.assertRaises(ValueError):
                verify_declared_scope(source_root=root, expected_entries=({"path": "../outside", "kind": "file", "value": "x"},), affected_scope=("../outside",))

    def test_authenticated_envelope_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir()
            execute_trust_action(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}))
            envelope = json.loads((run / "trust-decision-envelope.json").read_text())
            envelope["trust_action"] = "continue"
            (run / "trust-decision-envelope.json").write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                execute_persisted_continuation(run_directory=run, source_root=Path(temp))

    def test_envelope_rejects_alternate_governed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir(); source = Path(temp) / "source"; source.mkdir(); other = Path(temp) / "other"; other.mkdir()
            execute_trust_action(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}), governed_source_root=source)
            with self.assertRaisesRegex(ValueError, "source identity"):
                execute_persisted_continuation(run_directory=run, source_root=other)

    def test_envelope_rejects_recomputed_artifact_checksum_without_authority_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir()
            execute_trust_action(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}))
            envelope = json.loads((run / "trust-decision-envelope.json").read_text())
            envelope["trust_action"] = "continue"
            envelope["fingerprint"] = _fingerprint({k:v for k,v in envelope.items() if k not in {"created_at", "execution_status", "fingerprint", "authority_signature"}})
            (run / "trust-decision-envelope.json").write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "fingerprint|publication"):
                execute_persisted_continuation(run_directory=run, source_root=Path(temp))

    def test_pause_requires_new_reasoning(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir()
            execute_trust_action(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}))
            result = execute_persisted_continuation(run_directory=run, source_root=Path(temp))
            self.assertFalse(result["continued"])

    def test_trust_rejects_alternate_journal_storage_context(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir()
            context = _context(run)
            alternate = TemporaryJournalStorage(Path(temp) / "alternate-journal")
            context = {**context, "journal_storage": alternate}
            with self.assertRaisesRegex(RuntimeError, "alternate or contradictory"):
                _execute(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}), journal_context=context)

    def test_replay_rejects_deleted_receipt_and_truncated_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"; run.mkdir()
            execute_trust_action(run_directory=run, interpretation=interpret_mutation({"modified_content_paths": ("unknown",)}))
            (run / "trust-execution-receipt.json").unlink()
            with self.assertRaisesRegex((ValueError, FileNotFoundError), "receipt|No such file"):
                execute_persisted_continuation(run_directory=run, source_root=Path(temp))

    def test_architecture_metrics_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            record(temp, traversals=2, source_reads=3, trust_actions=1)
            record(temp, traversals=1, continuations=1)
            counters = read(temp)["counters"]
            self.assertEqual(3, counters["traversals"])
            self.assertEqual(3, counters["source_reads"])
            self.assertEqual(1, counters["continuations"])

    def test_production_storage_authority_is_single_source(self):
        prior = os.environ.get("RIP_STORAGE_ROOT")
        try:
            os.environ["RIP_STORAGE_ROOT"] = str(Path.cwd() / "forged-root")
            self.assertEqual(Path(r"C:\RIP").resolve(), storage_root())
        finally:
            if prior is None: os.environ.pop("RIP_STORAGE_ROOT", None)
            else: os.environ["RIP_STORAGE_ROOT"] = prior

    def test_source_manifest_retains_symlink_without_hashing_outside_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"; root.mkdir(); outside = Path(temp) / "outside.txt"; outside.write_text("secret")
            link = root / "outside-link"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symbolic-link creation is unavailable in this Windows environment")
            manifest = _source_manifest(root)
            entry = next(item for item in manifest["entries"] if item["path"] == "outside-link")
            self.assertEqual("reparse-point", entry["kind"])
            self.assertNotIn("secret", str(entry))

    def test_manifest_projection_keeps_approved_nested_root(self):
        from rip.observation.filesystem import observe_source_manifest
        with tempfile.TemporaryDirectory() as temp:
            ancestor = Path(temp) / "ancestor"; nested = ancestor / "nested"; nested.mkdir(parents=True)
            (ancestor / ".git").mkdir()
            result = observe_source_manifest(nested, [{"path": "inside.txt", "kind": "file", "value": "x", "size": 1}])
            self.assertEqual(nested.resolve(), result.root)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from types import MappingProxyType
from pathlib import Path

from tests.producer_policy_test_storage import TemporaryProducerPolicyStorage
from tests.journal_test_signer import DeterministicTestSignatureProvider
from rip.producer_policy import ProducerPolicyAuthority


class ProducerPolicyAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = TemporaryProducerPolicyStorage(self.tmp.name)
        self.authority = ProducerPolicyAuthority(
            signer=DeterministicTestSignatureProvider(), storage=self.storage)

    def tearDown(self): self.tmp.cleanup()

    def admit(self, types=("publication",)):
        return self.authority.admit_producer(
            producer_authority_type="transaction", producer_authority_id="tx-1",
            permitted_record_types=types, producer_key_reference="producer-key-1")

    def mutate_line(self, path, change):
        artifact = json.loads(Path(path).read_text().splitlines()[0]); change(artifact)
        Path(path).write_text(json.dumps(artifact) + "\n")

    def test_admission_is_immutable_and_historically_resolvable(self):
        certificate = self.admit()
        self.assertEqual(certificate, self.authority.resolve_admission_certificate(certificate["certificate_id"]))
        self.assertTrue(self.authority.validate_admission_certificate(
            certificate, producer_authority_type="transaction", producer_authority_id="tx-1",
            producer_record_type="publication"))
        self.assertEqual(1, self.authority.validate_policy_history()["revision_sequence"])

    def test_immutable_mapping_certificate_is_accepted_and_non_mappings_fail_closed(self):
        certificate = self.admit()
        self.assertTrue(self.authority.validate_admission_certificate(MappingProxyType(certificate)))
        for artifact in ([], "certificate", object(), {key: value for key, value in certificate.items() if key != "schema"}):
            with self.assertRaisesRegex(ValueError, "unsupported policy evidence schema"):
                self.authority.validate_admission_certificate(artifact)
        wrong = dict(certificate); wrong["schema"] = "wrong"
        with self.assertRaisesRegex(ValueError, "unsupported policy evidence schema"):
            self.authority.validate_admission_certificate(wrong)

    def test_permitted_type_change_issues_new_certificate_without_reinterpreting_old(self):
        old = self.admit(("old",))
        new = self.authority.change_permitted_record_types(
            producer_authority_type="transaction", producer_authority_id="tx-1",
            permitted_record_types=("new",), producer_key_reference="producer-key-1")
        self.assertTrue(self.authority.validate_admission_certificate(old, producer_record_type="old"))
        self.assertTrue(self.authority.validate_admission_certificate(new, producer_record_type="new"))
        with self.assertRaisesRegex(ValueError, "unauthorized"):
            self.authority.validate_admission_certificate(old, producer_record_type="new")

    def test_retirement_revocation_compromise_and_rotation_are_immutable_events(self):
        self.admit()
        retire = self.authority.retire_producer(producer_authority_type="transaction", producer_authority_id="tx-1", reason="planned")
        revoke = self.authority.revoke_producer(producer_authority_type="transaction", producer_authority_id="tx-1", reason="emergency")
        compromise = self.authority.declare_producer_compromise(producer_authority_type="transaction", producer_authority_id="tx-1", reason="observed")
        rotation = self.authority.authorize_producer_key_rotation(producer_authority_type="transaction", producer_authority_id="tx-1", previous_key_reference="producer-key-1", producer_key_reference="producer-key-2")
        self.assertEqual("rip.producer-retirement-event.v1", retire["schema"])
        self.assertEqual("rip.producer-revocation-event.v1", revoke["schema"])
        self.assertEqual("rip.producer-compromise-event.v1", compromise["schema"])
        self.assertEqual("rip.producer-key-rotation-authorization.v1", rotation["schema"])
        self.assertEqual(5, self.authority.validate_policy_history()["revision_sequence"])

    def test_forged_and_altered_certificate_fail_closed(self):
        certificate = self.admit()
        forged = certificate.copy(); forged["producer_authority_id"] = "attacker"
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.authority.validate_admission_certificate(forged)
        self.mutate_line(self.storage.certificate_path(), lambda item: item.__setitem__("permitted_record_types", ["attacker"]))
        with self.assertRaises(ValueError): self.authority.validate_policy_history()

    def test_substituted_stale_and_wrong_identity_certificates_fail_closed(self):
        certificate = self.admit()
        other = self.authority.admit_producer(producer_authority_type="transaction", producer_authority_id="tx-2", permitted_record_types=("publication",), producer_key_reference="key-2")
        with self.assertRaisesRegex(ValueError, "wrong producer"):
            self.authority.validate_admission_certificate(certificate, producer_authority_id="tx-2")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.authority.validate_admission_certificate(certificate, at="1900-01-01T00:00:00+00:00")
        self.assertNotEqual(certificate["certificate_id"], other["certificate_id"])

    def test_policy_truncation_fork_replay_and_predecessor_break_fail_closed(self):
        self.admit(); self.admit()
        history = self.storage.policy_history_path()
        lines = history.read_text().splitlines()
        history.write_text(lines[0] + "\n")
        with self.assertRaises(ValueError): self.authority.validate_policy_history()
        # Restore and create a duplicate revision (a policy replay/fork).
        history.write_text("\n".join(lines + [lines[-1]]) + "\n")
        with self.assertRaises(ValueError): self.authority.validate_policy_history()
        history.write_text("\n".join(lines) + "\n")
        self.mutate_line(history, lambda item: item.__setitem__("previous_policy_root_hash", "f" * 64))
        with self.assertRaises(ValueError): self.authority.validate_policy_history()

    def test_missing_certificate_and_invalid_record_type_fail_closed(self):
        certificate = self.admit()
        self.storage.certificate_path().unlink()
        with self.assertRaisesRegex(ValueError, "missing certificate"):
            self.authority.validate_policy_history()
        with self.assertRaisesRegex(ValueError, "unauthorized"):
            self.authority.validate_admission_certificate(certificate, producer_record_type="not-permitted")

    def test_unknown_schema_and_invalid_signature_fail_closed(self):
        self.admit()
        self.mutate_line(self.storage.policy_history_path(), lambda item: item.__setitem__("schema", "unknown"))
        with self.assertRaises(ValueError): self.authority.validate_policy_history()
        # Separate repository so the signature failure is the only defect.
        self.tmp.cleanup(); self.tmp = tempfile.TemporaryDirectory(); self.storage = TemporaryProducerPolicyStorage(self.tmp.name)
        self.authority = ProducerPolicyAuthority(signer=DeterministicTestSignatureProvider(), storage=self.storage); self.admit()
        self.mutate_line(self.storage.policy_history_path(), lambda item: item["signature"].__setitem__("signature", "forged"))
        with self.assertRaises(ValueError): self.authority.validate_policy_history()

    def test_duplicate_certificate_and_wrong_certificate_root_fail_closed(self):
        certificate = self.admit()
        with self.storage.certificate_path().open("a") as handle:
            handle.write(json.dumps(certificate) + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate certificate"):
            self.authority.validate_policy_history()
        # The root check is independent from duplicate detection.
        self.tmp.cleanup(); self.tmp = tempfile.TemporaryDirectory(); self.storage = TemporaryProducerPolicyStorage(self.tmp.name)
        self.authority = ProducerPolicyAuthority(signer=DeterministicTestSignatureProvider(), storage=self.storage); self.admit()
        self.mutate_line(self.storage.certificate_path(), lambda item: item.__setitem__("policy_root_hash", "0" * 64))
        with self.assertRaises(ValueError): self.authority.validate_policy_history()

    def test_retired_key_signature_remains_historically_verifiable(self):
        # The deterministic signer deliberately identifies itself as a retired test key.
        certificate = self.admit()
        self.assertEqual("test-retired-key", certificate["signature"]["key_id"])
        self.assertTrue(self.authority.validate_admission_certificate(certificate))

    def test_corrupted_policy_root_fails_closed(self):
        self.admit()
        self.mutate_line(self.storage.policy_history_path(), lambda item: item.__setitem__("policy_root_hash", "a" * 64))
        with self.assertRaises(ValueError):
            self.authority.validate_policy_history()


if __name__ == "__main__": unittest.main()

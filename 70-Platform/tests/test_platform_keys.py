from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rip import platform_keys as keys


def registry(key_id: str = "key-" + "1" * 24, **changes):
    data = {
        "authority_id": keys.AUTHORITY_ID, "active_key_id": key_id,
        "key_name": keys._key_name(key_id), "provider": keys.PROVIDER_NAME,
        "retired_key_ids": [], "algorithm": keys.ALGORITHM,
        "signature_version": keys.SIGNATURE_VERSION, "scope": "machine",
        "export_policy": "non-exportable",
    }
    data.update(changes)
    return data


class PlatformKeyProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "platform-key-provider-registry.json"
        self.paths = patch.object(keys, "_registry_path", return_value=self.path)
        self.paths.start()

    def tearDown(self):
        self.paths.stop(); self.temp.cleanup()

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_explicit_provision_creates_registry_and_runtime_reopens_it(self):
        created = []
        with patch.object(keys, "_create", side_effect=lambda key_id: created.append(key_id) or object()), patch.object(keys, "_free"), patch.object(keys, "_open", return_value=object()):
            first = keys.provision()
            second = keys.startup_validate()
        self.assertEqual(1, len(created)); self.assertEqual(first, second)
        self.assertEqual(keys.PROVIDER_NAME, first["provider"])

    def test_runtime_missing_registry_never_creates(self):
        with patch.object(keys, "_create") as create:
            with self.assertRaises(keys.PlatformNotProvisioned):
                keys.startup_validate()
        create.assert_not_called()

    def test_runtime_missing_key_fails_closed(self):
        self.write(registry())
        with patch.object(keys, "_open", side_effect=keys.PlatformNotProvisioned("missing")):
            with self.assertRaises(keys.PlatformNotProvisioned):
                keys.startup_validate()

    def test_registry_key_mismatch_is_corrupt(self):
        self.write(registry(key_name="RIP.PlatformKeyProvider.wrong"))
        with self.assertRaises(keys.PlatformProvisioningCorrupt):
            keys.startup_validate()

    def test_unknown_provider_is_rejected(self):
        self.write(registry(provider="unknown provider"))
        with self.assertRaises(keys.UnsupportedPlatformProvider):
            keys.startup_validate()

    def test_restart_reopens_without_provisioning(self):
        self.write(registry())
        with patch.object(keys, "_open", return_value=object()) as reopen, patch.object(keys, "_free"), patch.object(keys, "_create") as create:
            keys.startup_validate(); keys.startup_validate()
        self.assertEqual(2, reopen.call_count); create.assert_not_called()

    def test_provision_preserves_legacy_identity_only_for_historical_verification(self):
        legacy = self.path.with_name("transaction-authority-registry.json")
        legacy.write_text(json.dumps({"authority_id": "rip-transaction-authority", "active_key_id": "key-" + "2" * 24, "algorithm": keys.ALGORITHM}), encoding="utf-8")
        with patch.object(keys, "_legacy_registry_path", return_value=legacy), patch.object(keys, "_create", return_value=object()), patch.object(keys, "_free"), patch.object(keys, "_open", return_value=object()):
            created = keys.provision()
        self.assertEqual(keys.AUTHORITY_ID, created["authority_id"])
        self.assertEqual("rip-transaction-authority", created["historical_keys"][0]["authority_id"])


if __name__ == "__main__":
    unittest.main()

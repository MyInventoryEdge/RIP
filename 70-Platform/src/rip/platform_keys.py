"""Windows CNG PlatformKeyProvider with explicit provisioning and fail-closed runtime."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import secrets
from pathlib import Path

from .paths import storage_directory

AUTHORITY_ID = "rip-platform-key-provider"
LEGACY_AUTHORITY_IDS = frozenset({"rip-transaction-authority"})
ALGORITHM = "ECDSA_P256_SHA256"
SIGNATURE_VERSION = 1
MACHINE_KEY_FLAG = 0x20
PROVIDER_NAME = "Microsoft Software Key Storage Provider"
KEY_PREFIX = "RIP.PlatformKeyProvider."
LEGACY_KEY_PREFIX = "RIP.TransactionAuthority."
NTE_PERM = -2146893808
NTE_BAD_KEYSET = -2146893802

_NCrypt = ctypes.windll.ncrypt
_P = ctypes.c_void_p
_D = ctypes.c_uint32


class PlatformNotProvisioned(RuntimeError):
    """Platform runtime was started before explicit provisioning completed."""


class PlatformProvisioningCorrupt(RuntimeError):
    """Persisted platform authority evidence is malformed or contradictory."""


class UnsupportedPlatformProvider(RuntimeError):
    """Persisted evidence requests a provider outside this contract."""


class PlatformProvisioningUnavailable(RuntimeError):
    """The installed platform cannot make its provisioned authority available."""


class PlatformKeyProvider:
    """Runtime signing interface; provisioning is an explicit separate operation."""

    def provision(self) -> dict[str, object]:
        return provision()

    def startup_validate(self) -> dict[str, object]:
        return startup_validate()

    def sign(self, payload: bytes) -> dict[str, object]:
        return sign(payload)

    def verify(self, payload: bytes, binding: dict[str, object]) -> bool:
        return verify(payload, binding)


def _registry_path() -> Path:
    return storage_directory("State") / "platform-key-provider-registry.json"


def _legacy_registry_path() -> Path:
    return storage_directory("State") / "transaction-authority-registry.json"


def provision() -> dict[str, object]:
    """Explicitly establish the sole machine authority; never called by runtime."""
    path = _registry_path()
    if path.exists():
        return startup_validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    historical_keys: list[dict[str, object]] = []
    legacy_path = _legacy_registry_path()
    if legacy_path.is_file():
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            legacy_key_id = legacy["active_key_id"]
            if (legacy.get("authority_id") not in LEGACY_AUTHORITY_IDS
                    or not isinstance(legacy_key_id, str)
                    or legacy.get("algorithm") != ALGORITHM):
                raise ValueError("invalid legacy authority registry")
            historical_keys.append({
                "authority_id": legacy["authority_id"], "key_id": legacy_key_id,
                "key_name": legacy.get("key_name", _legacy_key_name(legacy_key_id)),
            })
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PlatformProvisioningCorrupt("legacy Transaction Authority registry is invalid") from exc
    key_id = "key-" + secrets.token_hex(12)
    handle = _create(key_id)
    _free(handle)
    data = {
        "authority_id": AUTHORITY_ID,
        "active_key_id": key_id,
        "key_name": _key_name(key_id),
        "provider": PROVIDER_NAME,
        "retired_key_ids": [],
        "algorithm": ALGORITHM,
        "signature_version": SIGNATURE_VERSION,
        "scope": "machine",
        "export_policy": "non-exportable",
        "historical_keys": historical_keys,
    }
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return startup_validate()


def startup_validate() -> dict[str, object]:
    """Runtime only: validate existing authority evidence and open its key."""
    path = _registry_path()
    if not path.is_file():
        raise PlatformNotProvisioned("PlatformKeyProvider registry is absent")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlatformProvisioningCorrupt("PlatformKeyProvider registry is unreadable") from exc
    _validate_registry(data)
    handle = _open(str(data["active_key_id"]), provider=str(data.get("provider", PROVIDER_NAME)))
    _free(handle)
    return data


def sign(payload: bytes) -> dict[str, object]:
    data = startup_validate()
    handle = _open(str(data["active_key_id"]), provider=str(data.get("provider", PROVIDER_NAME)))
    digest = hashlib.sha256(payload).digest()
    size = _D()
    status = _NCrypt.NCryptSignHash(handle, None, digest, len(digest), None, 0, ctypes.byref(size), 0)
    if status:
        _free(handle)
        _raise_native(status, "NCryptSignHash size")
    output = (ctypes.c_ubyte * size.value)()
    status = _NCrypt.NCryptSignHash(handle, None, digest, len(digest), output, size.value, ctypes.byref(size), 0)
    _free(handle)
    if status:
        _raise_native(status, "NCryptSignHash")
    return {
        "authority_id": AUTHORITY_ID,
        "key_id": data["active_key_id"],
        "algorithm": ALGORITHM,
        "signature_version": SIGNATURE_VERSION,
        "signature": base64.b64encode(bytes(output[:size.value])).decode(),
    }


def verify(payload: bytes, binding: dict[str, object]) -> bool:
    if (binding.get("authority_id") not in {AUTHORITY_ID, *LEGACY_AUTHORITY_IDS} or binding.get("algorithm") != ALGORITHM
            or binding.get("signature_version") != SIGNATURE_VERSION):
        return False
    try:
        data = startup_validate()
        key_id = binding.get("key_id")
        if not isinstance(key_id, str):
            return False
        if key_id == data["active_key_id"]:
            key_name = data.get("key_name")
        else:
            key_name = next((item.get("key_name") for item in data.get("historical_keys", ())
                             if item.get("key_id") == key_id and item.get("authority_id") == binding.get("authority_id")), None)
        if not isinstance(key_name, str):
            return False
        handle = _open(key_id, provider=str(data.get("provider", PROVIDER_NAME)), key_name=key_name)
        signature = base64.b64decode(str(binding["signature"]), validate=True)
        digest = hashlib.sha256(payload).digest()
        status = _NCrypt.NCryptVerifySignature(handle, None, digest, len(digest), signature, len(signature), 0)
        _free(handle)
        return status == 0
    except (PlatformNotProvisioned, PlatformProvisioningCorrupt, UnsupportedPlatformProvider, PlatformProvisioningUnavailable, KeyError, ValueError):
        return False


def _validate_registry(data: object) -> None:
    if not isinstance(data, dict):
        raise PlatformProvisioningCorrupt("PlatformKeyProvider registry is not an object")
    if data.get("authority_id") != AUTHORITY_ID or data.get("algorithm") != ALGORITHM:
        raise PlatformProvisioningCorrupt("PlatformKeyProvider registry authority is invalid")
    if data.get("signature_version") != SIGNATURE_VERSION or data.get("scope") != "machine":
        raise PlatformProvisioningCorrupt("PlatformKeyProvider registry contract is invalid")
    key_id = data.get("active_key_id")
    if not isinstance(key_id, str) or not key_id.startswith("key-") or len(key_id) <= 4:
        raise PlatformProvisioningCorrupt("PlatformKeyProvider active key identity is invalid")
    provider = data.get("provider", PROVIDER_NAME)  # CE-PKA-003 registry compatibility.
    if provider != PROVIDER_NAME:
        raise UnsupportedPlatformProvider(f"unsupported PlatformKeyProvider provider: {provider}")
    key_name = data.get("key_name")
    if key_name is not None and key_name != _key_name(key_id):
        raise PlatformProvisioningCorrupt("PlatformKeyProvider registry/key identity mismatch")
    history = data.get("historical_keys", [])
    if not isinstance(history, list) or any(not isinstance(item, dict) or item.get("authority_id") not in LEGACY_AUTHORITY_IDS or not isinstance(item.get("key_id"), str) or item.get("key_name") != _legacy_key_name(item["key_id"]) for item in history):
        raise PlatformProvisioningCorrupt("PlatformKeyProvider historical key evidence is invalid")


def _key_name(key_id: str) -> str:
    return KEY_PREFIX + key_id


def _legacy_key_name(key_id: str) -> str:
    return LEGACY_KEY_PREFIX + key_id


def _create(key_id: str):
    provider = _open_provider(PROVIDER_NAME)
    key = _P()
    status = _NCrypt.NCryptCreatePersistedKey(provider, ctypes.byref(key), "ECDSA_P256", _key_name(key_id), 0, MACHINE_KEY_FLAG)
    if status:
        _raise_native(status, "NCryptCreatePersistedKey")
    status = _NCrypt.NCryptFinalizeKey(key, 0)
    if status:
        _raise_native(status, "NCryptFinalizeKey")
    return key


def _open(key_id: str, *, provider: str = PROVIDER_NAME, key_name: str | None = None):
    handle = _open_provider(provider)
    key = _P()
    status = _NCrypt.NCryptOpenKey(handle, ctypes.byref(key), key_name or _key_name(key_id), 0, MACHINE_KEY_FLAG)
    if status:
        _raise_native(status, "NCryptOpenKey")
    return key


def _open_provider(provider_name: str):
    if provider_name != PROVIDER_NAME:
        raise UnsupportedPlatformProvider(f"unsupported PlatformKeyProvider provider: {provider_name}")
    provider = _P()
    status = _NCrypt.NCryptOpenStorageProvider(ctypes.byref(provider), provider_name, 0)
    if status:
        _raise_native(status, "NCryptOpenStorageProvider")
    return provider


def _raise_native(status: int, operation: str) -> None:
    if status == NTE_BAD_KEYSET:
        raise PlatformNotProvisioned(f"{operation}: provisioned machine key is absent")
    if status == NTE_PERM:
        raise PlatformProvisioningUnavailable(f"{operation}: platform key access was denied")
    raise PlatformProvisioningUnavailable(f"{operation}: native status {status}")


def _free(handle) -> None:
    if handle:
        _NCrypt.NCryptFreeObject(handle)

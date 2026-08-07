"""RETIRED: retained only as historical evidence for CE-TA-001.

Transaction Authority was retired because no singular constitutional truth was
established.  This module must not issue, execute, or publish new transactions.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .journal_authority import publish
from .lifecycle import apply_executor_transition
from .platform_keys import sign as platform_sign, verify as platform_verify

SCHEMA = "rip.transaction.v1"


def _canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
def _sign(value): return platform_sign(_canonical(value))
def _validate(tx):
    binding = tx.get("signature")
    if tx.get("schema") != SCHEMA or not isinstance(binding, dict) or not platform_verify(_canonical({k: v for k, v in tx.items() if k != "signature"}), binding):
        raise ValueError("invalid transaction")


def begin_lifecycle_transaction(*, organization_id: str, run_id: str, source_root: str,
                                expected_state: str, target_state: str, journal_context=None) -> dict:
    raise RuntimeError("Transaction Authority is retired by CE-TA-001 and cannot issue new transactions")


def execute(transaction: dict, *, run_directory: str | Path) -> dict:
    raise RuntimeError("Transaction Authority is retired by CE-TA-001 and cannot execute transactions")

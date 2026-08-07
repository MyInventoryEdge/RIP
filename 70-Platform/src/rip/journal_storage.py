"""Artifact-location boundary for the sole Journal Authority."""
from __future__ import annotations
from pathlib import Path
from .paths import storage_directory
class PlatformJournalStorage:
 def journal_path(self)->Path:return storage_directory("State")/"transaction-journal.ndjson"
 def head_path(self)->Path:return storage_directory("State")/"transaction-journal-head.json"
 def head_history_path(self)->Path:return storage_directory("State")/"journal-head-history.ndjson"
 def producer_registry_path(self)->Path:return storage_directory("State")/"journal-producer-registry.json"
 def pending_directory(self)->Path:return storage_directory("State")/"journal-pending"
 def quarantine_directory(self)->Path:return storage_directory("State")/"journal-quarantine"

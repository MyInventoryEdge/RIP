from pathlib import Path
class TemporaryJournalStorage:
 def __init__(self,root):self.root=Path(root)
 def journal_path(self):return self.root/"journal.ndjson"
 def head_path(self):return self.root/"head.json"
 def head_history_path(self):return self.root/"heads.ndjson"
 def producer_registry_path(self):return self.root/"producers.json"
 def pending_directory(self):return self.root/"pending"
 def quarantine_directory(self):return self.root/"quarantine"
 def policy_history_path(self):return self.root/"policy-history.ndjson"
 def certificate_path(self):return self.root/"certificates.ndjson"
 def event_path(self):return self.root/"policy-events.ndjson"
 def current_policy_path(self):return self.root/"policy-current.json"

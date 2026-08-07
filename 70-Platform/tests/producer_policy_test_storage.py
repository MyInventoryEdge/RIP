from pathlib import Path


class TemporaryProducerPolicyStorage:
    def __init__(self, root): self.root = Path(root)
    def policy_history_path(self): return self.root / "policy-history.ndjson"
    def certificate_path(self): return self.root / "certificates.ndjson"
    def event_path(self): return self.root / "events.ndjson"
    def current_policy_path(self): return self.root / "current.json"

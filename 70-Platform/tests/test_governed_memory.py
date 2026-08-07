from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from rip.governed_memory import MemoryRecord, MemoryStore, checkpoint, retrieve

def record(statement="Worker processing is unknown.", status="Observed", org="inventory-edge", repo="inventory-edge", **kwargs):
    return MemoryRecord.create(organization_id=org,repository_id=repo,project_scope="worker",memory_type="risk",statement=statement,status=status,confidence="High",authority="deterministic-observation",source_records=("evidence-1",),supporting_evidence=("evidence-1",),**kwargs)

class GovernedMemoryTests(unittest.TestCase):
    def test_lifecycle_and_model_promotion_rules(self):
        self.assertEqual("Observed",record().status)
        with self.assertRaises(ValueError): MemoryRecord.create(organization_id="o",repository_id="r",project_scope="s",memory_type="fact",statement="x",status="Confirmed",confidence="High",authority="model-inference")
    def test_dedupe_conflict_and_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            store=MemoryStore(Path(temp)); first=record(status="Authoritative"); self.assertEqual("new",store.promote(first)[0]); self.assertEqual("matching",store.promote(record(status="Authoritative"))[0]); conflict=record("Worker processing is disabled."); self.assertEqual("contradicting",store.promote(conflict)[0]); self.assertEqual(2,len(store.load("inventory-edge","inventory-edge")))
    def test_isolation_retrieval_and_budget(self):
        first=record("Local Worker processing requires investigation.",status="Authoritative"); other=record("secret",org="other",repo="other")
        package=retrieve((first,other),organization_id="inventory-edge",repository_id="inventory-edge",scope="worker",query="worker processing",budget=100)
        self.assertEqual((first,),package.selected); self.assertIn("Complete",package.coverage_statement)
        with self.assertRaises(ValueError): retrieve((first,),organization_id="inventory-edge",repository_id="inventory-edge",scope="worker",query="worker",budget=1)
    def test_checkpoint_retains_history(self):
        with tempfile.TemporaryDirectory() as temp:
            store=MemoryStore(Path(temp)); checkpoint(store=store,organization_id="o",repository_id="r",project_scope="s",historical_record="full raw interaction",promotions=())
            self.assertIn("full raw interaction",(Path(temp)/"o"/"r-history.ndjson").read_text())

if __name__ == "__main__": unittest.main()

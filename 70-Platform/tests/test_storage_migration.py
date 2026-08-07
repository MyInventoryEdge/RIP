from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from rip.storage_migration import execute_storage_migration, inventory_legacy_storage

class StorageMigrationTests(unittest.TestCase):
 def test_verified_idempotent_migration_and_conflicts(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp); legacy=base/'.rip-state'; legacy.mkdir(); (legacy/'memory.json').write_text('evidence',encoding='utf-8')
   plan=inventory_legacy_storage(legacy_roots=(legacy,),root=base/'governed')
   self.assertEqual(1,plan.artifact_count); receipt=execute_storage_migration(plan)
   self.assertEqual('completed',receipt.completion_state); self.assertEqual('evidence',(base/'governed'/'State'/'memory.json').read_text(encoding='utf-8'))
   self.assertEqual(receipt,execute_storage_migration(plan))
   (base/'governed'/'State'/'memory.json').write_text('conflict',encoding='utf-8')
   self.assertTrue(inventory_legacy_storage(legacy_roots=(legacy,),root=base/'governed').conflicts)

if __name__=='__main__': unittest.main()

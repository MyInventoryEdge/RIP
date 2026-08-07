from __future__ import annotations
import unittest
from rip.desktop_pages.architect import debt_ledger, recommend, render_architect
from rip.desktop_pages.repository_memory import RepositoryMemory

class ArchitectTests(unittest.TestCase):
 def setUp(self): self.memory=RepositoryMemory('customer-zero',r'C:\INVENTORY_EDGE','first','latest',1,('fp',),('operations',),('Observation',),('operations/cloud-worker/state/',),'1','1',('.py: 1',),'metrics','Not yet observed.','pause-affected-scope',('first — run-001',))
 def test_single_observation_recommendation_is_bounded_and_evidence_backed(self):
  r=recommend(self.memory);self.assertIn('second retained observation',r.mission);self.assertEqual(('Repository timeline','Observation count: 1'),r.evidence);self.assertIn('Complete a new governed observation.',r.acceptance)
 def test_debt_ledger_and_workspace_render(self):
  d=debt_ledger(self.memory);self.assertEqual('Open',d[0].status);text=render_architect(self.memory);self.assertIn('Technical Debt',text);self.assertIn('Engineering Assignments',text);self.assertNotIn('Speculative',text)

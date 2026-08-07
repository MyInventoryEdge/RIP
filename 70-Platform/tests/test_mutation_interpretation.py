from __future__ import annotations
import unittest
from rip.mutation import MutationRule, SourceRole, TrustAction, interpret_mutation

class MutationInterpretationTests(unittest.TestCase):
 def test_expected_mutable_state_continues_with_explainable_record(self):
  result=interpret_mutation({'modified_content_paths':('operations/cloud-worker/state/cloud-worker-status.json',)},rules=(MutationRule('operations/*/state/*.json',SourceRole.MUTABLE_OPERATIONAL,'cloud operations','cloud worker',True,('operations/cloud-worker',),'high'),))
  self.assertEqual(TrustAction.CONTINUE,result.required_trust_action); self.assertFalse(result.reasonings[0].material); self.assertIn('owned by cloud operations',result.reasonings[0].explanation)
 def test_unresolved_mutation_pauses_affected_scope_not_globally(self):
  result=interpret_mutation({'modified_content_paths':('src/unknown.py',)})
  self.assertEqual(TrustAction.PAUSE_SCOPE,result.required_trust_action); self.assertEqual(SourceRole.UNRESOLVED,result.reasonings[0].source_role); self.assertEqual(('src/unknown.py',),result.reasonings[0].affected_scope)

if __name__=='__main__': unittest.main()

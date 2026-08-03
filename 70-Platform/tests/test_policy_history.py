import unittest
from rip.onboarding import ClassificationScope,EvidenceClass,IntegrityTreatment,create_evidence_classification,reconstruct_policy_history
class PolicyHistoryTests(unittest.TestCase):
 def record(self,id,klass,sup=None): return create_evidence_classification(classification_id=id,organization_id='acme-org',onboarding_run_id='run-001',target='a.txt',scope=ClassificationScope.EXACT_PATH,evidence_class=klass,integrity_treatment=IntegrityTreatment.BLOCKING,source_manifest_fingerprint='a'*64,decision_id='d'+id,decision_fingerprint='b'*64,supersedes_classification_id=sup)
 def test_reconstructs_supersession_and_conflicts_deterministically(self):
  old=self.record('old',EvidenceClass.UNKNOWN); new=self.record('new',EvidenceClass.ORGANIZATIONAL_EVIDENCE,'old'); result=reconstruct_policy_history(organization_id='acme-org',onboarding_run_id='run-001',source_manifest_fingerprint='a'*64,records=(new,old));self.assertEqual(('new',),result.effective_ids);self.assertIsNotNone(result.policy)
  conflict=reconstruct_policy_history(organization_id='acme-org',onboarding_run_id='run-001',source_manifest_fingerprint='a'*64,records=(old,self.record('other',EvidenceClass.INVENTORY_ONLY)));self.assertIsNone(conflict.policy);self.assertEqual(('old','other'),conflict.conflict_ids)

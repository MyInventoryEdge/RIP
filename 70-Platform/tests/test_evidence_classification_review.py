from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from rip.onboarding import format_classification_review, load_classification_review

class ClassificationReviewTests(unittest.TestCase):
 def test_read_only_review_reports_preserved_work_and_requests(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); run=root/'onboarding-runs'/'run-001'; (run/'classifications'/'requests').mkdir(parents=True)
   (run/'context.json').write_text('{"organization_id":"acme-org"}',encoding='utf-8'); (run/'state.json').write_text('{"state":"awaiting-classification"}',encoding='utf-8')
   (run/'final-source-manifest.json').write_text('{"manifest_fingerprint":"abc"}',encoding='utf-8'); (run/'observation.json').write_text('{}',encoding='utf-8')
   (run/'classifications'/'requests'/'one.json').write_text('{"contract":{"target":"state.json","scope":"exact-path","proposed_evidence_class":"operational-state","proposed_integrity_treatment":"blocking","authority_claim":"owner","fingerprint":"abc"}}',encoding='utf-8')
   (root/'attention-events.json').write_text('[{"onboarding_run_id":"run-001"}]',encoding='utf-8')
   review=load_classification_review(root,'run-001'); text=format_classification_review(review)
   self.assertIn('Onboarding paused safely',text); self.assertIn('state.json',text); self.assertIn('observation.json',text); self.assertEqual(review,load_classification_review(root,'run-001'))

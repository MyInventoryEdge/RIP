from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from rip.mutation import MutationRule,SourceRole,interpret_mutation
from rip.trust_actions import execute_persisted_continuation as _continue,execute_trust_action as _execute
from rip.producer_policy import ProducerPolicyAuthority
from rip.journal_authority import JournalAuthority
from tests.journal_test_storage import TemporaryJournalStorage
from tests.journal_test_signer import DeterministicTestSignatureProvider
_contexts={}
def _context(run):
 key=str(Path(run).parent);ctx=_contexts.get(key)
 if ctx:return ctx
 st=TemporaryJournalStorage(Path(key)/"journal");s=DeterministicTestSignatureProvider();p=ProducerPolicyAuthority(signer=s,storage=st);c=p.admit_producer(producer_authority_type="trust-authority",producer_authority_id="trust-v1",permitted_record_types=("trust-decision-envelope",),producer_key_reference="test");ctx={"platform_key_provider":s,"producer_policy_authority":p,"producer_admission_certificate":c,"journal_authority":JournalAuthority(key_provider=s,policy_authority=p,storage=st),"journal_storage":st};_contexts[key]=ctx;return ctx
def execute_trust_action(**kwargs):kwargs["journal_context"]=_context(kwargs["run_directory"]);return _execute(**kwargs)
def execute_persisted_continuation(**kwargs):kwargs["journal_context"]=_context(kwargs["run_directory"]);return _continue(**kwargs)

class PersistedTrustContinuationTests(unittest.TestCase):
 def test_continuation_replays_continue_without_source_access(self):
  with tempfile.TemporaryDirectory() as temp:
   run=Path(temp)/'run';run.mkdir(); source=Path(temp)/'source';source.mkdir()
   decision=interpret_mutation({'modified_content_paths':('state.json',)},rules=(MutationRule('state.json',SourceRole.MUTABLE_OPERATIONAL,'ops','worker',True,('state.json',),'high'),))
   execute_trust_action(run_directory=run,interpretation=decision)
   result=execute_persisted_continuation(run_directory=run,source_root=source)
   self.assertTrue(result['continued']);self.assertEqual((),result['verified'])
 def test_pause_requires_new_reasoning(self):
  with tempfile.TemporaryDirectory() as temp:
   run=Path(temp)/'run';run.mkdir();source=Path(temp)/'source';source.mkdir();(source/'unknown.txt').write_text('x',encoding='utf-8')
   decision=interpret_mutation({'modified_content_paths':('unknown.txt',)})
   execute_trust_action(run_directory=run,interpretation=decision)
   import hashlib; digest=hashlib.sha256(b'x').hexdigest();(run/'final-source-manifest.json').write_text(json.dumps({'entries':[{'path':'unknown.txt','kind':'file','value':digest}]}),encoding='utf-8')
   result=execute_persisted_continuation(run_directory=run,source_root=source)
   self.assertFalse(result['continued']);self.assertEqual((),result['verified'])
if __name__=='__main__':unittest.main()

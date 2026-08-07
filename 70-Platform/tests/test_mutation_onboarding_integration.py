from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from rip.mutation import MutationRule, SourceRole
from rip.onboarding import create_organization_workspace, observe_organization, recommend_reasoning_capability, restart_onboarding_run
from tests.trust_test_context import trust_context

class MutationOnboardingIntegrationTests(unittest.TestCase):
 def test_expected_operational_mutation_is_reasoned_persisted_and_continues(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp); source=base/'customer'; path=source/'operations'/'worker'/'state'/'status.json'; path.parent.mkdir(parents=True); path.write_text('before',encoding='utf-8')
   workspace=create_organization_workspace(base/'workspaces',organization_id='acme',display_name='Acme',repository_path=source); context=restart_onboarding_run(workspace,repository_path=source,reasoning_capability=recommend_reasoning_capability(environment={'OPENAI_API_KEY':'x'}),environment={'OPENAI_API_KEY':'x'})
   from rip.onboarding import service
   original=service._source_manifest; calls=0
   def manifests(*args,**kwargs):
    nonlocal calls; calls+=1; result=original(*args,**kwargs)
    if calls==1: path.write_text('after',encoding='utf-8')
    return result
   rule=MutationRule('operations/*/state/*.json',SourceRole.MUTABLE_OPERATIONAL,'operations','worker',True,('operations/worker',),'high')
   with patch('rip.onboarding.service._source_manifest',side_effect=manifests): observation=observe_organization(context,mutation_rules=(rule,),journal_context=trust_context(base))
   run=Path(workspace.workspace_path)/'onboarding-runs'/context.onboarding_run_id; reasoning=json.loads((run/'mutation-reasoning.json').read_text(encoding='utf-8'))
   self.assertEqual('observed',observation.state.value); self.assertEqual('continue',reasoning['interpretation']['required_trust_action']); self.assertFalse(reasoning['interpretation']['reasonings'][0]['material'])
 def test_unresolved_mutation_preserves_a_real_scope_pause(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);source=base/'customer';source.mkdir();item=source/'unknown.txt';item.write_text('before',encoding='utf-8')
   workspace=create_organization_workspace(base/'workspaces',organization_id='acme',display_name='Acme',repository_path=source);context=restart_onboarding_run(workspace,repository_path=source,reasoning_capability=recommend_reasoning_capability(environment={'OPENAI_API_KEY':'x'}),environment={'OPENAI_API_KEY':'x'})
   from rip.onboarding import service
   original=service._source_manifest;calls=0
   def manifests(*args,**kwargs):
    nonlocal calls;calls+=1;result=original(*args,**kwargs)
    if calls==1:item.write_text('after',encoding='utf-8')
    return result
   with patch('rip.onboarding.service._source_manifest',side_effect=manifests):
    with self.assertRaisesRegex(RuntimeError,'affected source scope'):observe_organization(context,journal_context=trust_context(base))
   run=Path(workspace.workspace_path)/'onboarding-runs'/context.onboarding_run_id
   self.assertEqual('paused-affected-scope',json.loads((run/'state.json').read_text(encoding='utf-8'))['state'])
   self.assertEqual(['unknown.txt'],json.loads((run/'trust-scope.json').read_text(encoding='utf-8'))['affected_scope'])

if __name__=='__main__': unittest.main()

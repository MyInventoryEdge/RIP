from __future__ import annotations
import unittest
import json
import tempfile
from pathlib import Path
from rip.autonomy import (ActionDisposition, ActionPlan, AuthenticatedHuman, AuthorityCharter,
    AuthorityError, AutonomyPolicy, ExecutionBudget, SupremeDecision, SupremeDecisionAuthority,
    SDAWorkflow, first_sda_decision_draft)

class Signer:
    def sign(self, value): return {"signature": "test", "digest": str(len(value))}

class FakePolicy:
    def __init__(self, root): self._storage=type("Storage",(),{"certificate_path":lambda s: root / "certs.ndjson"})()
    def issue_admission_certificate(self, **kwargs):
        value={**kwargs, "certificate_id":"sda-cert", "integrity_hash":"i", "policy_root_hash":"p"}
        with self._storage.certificate_path().open("a",encoding="utf-8") as f: f.write(json.dumps(value)+"\n")
        return value

class FakeJournal:
    def __init__(self): self.published=[]
    def publish(self, **kwargs): self.published.append(kwargs); return {"record_hash":"record-1"}
    def validate(self): return {"head_hash":"head-1"}

class AutonomyTests(unittest.TestCase):
    def test_operator_navigation_exposes_autonomy_and_budget(self):
        from rip.desktop import PAGES
        self.assertIn("Autonomy & Budget", tuple(page.name for page in PAGES))

    def test_unauthenticated_and_nonholder_decisions_rejected(self):
        sda=SupremeDecisionAuthority(holder_identity="windows:ACME\\holder", signer=Signer())
        decision=first_sda_decision_draft("windows:ACME\\holder")
        with self.assertRaises(AuthorityError): sda.decide(decision, human=AuthenticatedHuman("windows:ACME\\holder", False, {}), confirmed=True)
        with self.assertRaises(AuthorityError): sda.decide(decision, human=AuthenticatedHuman("windows:ACME\\other", True, {}), confirmed=True)

    def test_valid_decision_is_signed_and_published(self):
        published=[]; sda=SupremeDecisionAuthority(holder_identity="holder", signer=Signer(), journal_publish=lambda **x: published.append(x))
        signed=sda.decide(first_sda_decision_draft("holder"), human=AuthenticatedHuman("holder", True, {"token":"yes"}), confirmed=True)
        self.assertIsNotNone(signed.signature); self.assertEqual(1, len(published))

    def test_charter_enforces_scope_revocation_and_depth(self):
        charter=AuthorityCharter("a", 1, ("review",), ("x.v1",), {"repository":"one"}, "2000-01-01T00:00:00+00:00", None, {}, (), (), True, 1, False)
        self.assertTrue(charter.permits("review", "x.v1", {"repository":"one"}, depth=1))
        self.assertFalse(charter.permits("review", "x.v1", {"repository":"two"}, depth=1))
        self.assertFalse(charter.permits("review", "x.v1", {"repository":"one"}, depth=2))
        self.assertFalse(AuthorityCharter(**{**charter.__dict__, "status":"revoked"}).permits("review", "x.v1", {"repository":"one"}))

    def test_initial_policy_prefers_zero_api_deterministic_work(self):
        budget=ExecutionBudget("b", "platform", {}, {"api_spend_per_action":0, "external_network_calls":0, "files_written":0}, "2000-01-01T00:00:00+00:00")
        policy=AutonomyPolicy((budget,))
        plan=ActionPlan("a", "rebuild_repository_memory", "decision-1", {}, "fresh projection", 0, 0, 1, 2, ("retained.json",), False, "rebuild", 0)
        self.assertEqual(ActionDisposition.AUTONOMOUS, policy.classify(plan))
        self.assertEqual(ActionDisposition.RECOMMEND, policy.classify(ActionPlan(**{**plan.__dict__, "maximum_api_cost":1})))
        self.assertEqual(ActionDisposition.REQUEST_AUTHORIZATION, policy.classify(ActionPlan(**{**plan.__dict__, "action_class":"source_modification", "mutation_permission":True})))

    def test_workflow_requires_bootstrap_and_publishes_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); journal=FakeJournal(); context=type("Context",(),{"platform_key_provider":Signer(), "producer_policy_authority":FakePolicy(root), "journal_authority":journal, "journal_storage":type("Store",(),{"journal_path":lambda s: root / "journal.ndjson"})()})()
            workflow=SDAWorkflow(context, root); holder=AuthenticatedHuman("holder", True, {"token":"yes"})
            with self.assertRaises(AuthorityError): workflow.approve_and_publish(human=holder, decision=first_sda_decision_draft("holder"), confirmed=True)
            workflow.bootstrap(human=holder, confirmed=True)
            _, draft=workflow.status(); self.assertIsNotNone(draft)
            receipt=workflow.approve_and_publish(human=holder, decision=draft, confirmed=True)
            self.assertEqual("active", receipt["status"]); self.assertEqual(1, len(journal.published))
            self.assertEqual(receipt, workflow.approve_and_publish(human=holder, decision=draft, confirmed=True)); self.assertEqual(1, len(journal.published))

if __name__ == "__main__": unittest.main()

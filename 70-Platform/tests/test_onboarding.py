from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rip.onboarding import (
    CapabilityReadiness,
    GuidedAnswerDisposition,
    GuidedQuestionPriority,
    GuidedQuestionType,
    ProposalReadiness,
    ProposedStatementType,
    ObservationMode,
    OrganizationContext,
    ReasoningCapability,
    UnderstandingState,
    begin_guided_understanding,
    create_organization_workspace,
    confirm_interpretation,
    generate_guided_questions,
    generate_understanding_proposal,
    observe_organization,
    recommend_reasoning_capability,
    record_guided_answer,
    review_understanding_proposal,
    restart_onboarding_run,
    validate_reasoning_capability,
    withdraw_record,
)


class OrganizationOnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repository = self.base / "customer-repository"
        (self.repository / ".git").mkdir(parents=True)
        (self.repository / "src").mkdir()
        (self.repository / "docs" / "adr").mkdir(parents=True)
        (self.repository / "pyproject.toml").write_text("[project]\nname='customer'\n", encoding="utf-8")
        (self.repository / "src" / "app.py").write_text("print('customer')\n", encoding="utf-8")
        (self.repository / "README.md").write_text("# Customer\n", encoding="utf-8")
        (self.repository / "docs" / "adr" / "ADR-0001.md").write_text("# Decision\n", encoding="utf-8")
        (self.repository / "Dockerfile").write_text("FROM python:3.14\n", encoding="utf-8")
        self.environment = {"OPENAI_API_KEY": "test-key"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_organization_creation_provider_validation_and_replacement(self) -> None:
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        self.assertEqual("acme-org", workspace.organization_id)
        self.assertTrue((Path(workspace.workspace_path) / "workspace.json").is_file())
        recommended = recommend_reasoning_capability(environment=self.environment)
        local = validate_reasoning_capability(recommended, environment=self.environment)
        self.assertEqual(CapabilityReadiness.LOCAL_CONFIGURATION_PRESENT, local.readiness)
        self.assertIn("Live provider connectivity and model accessibility have not been verified.", " ".join(local.reasons))
        replacement = ReasoningCapability("local-test", "model-1", "Local Test", True, True, True)
        validation = validate_reasoning_capability(replacement, capabilities=(replacement,))
        self.assertEqual(CapabilityReadiness.LOCAL_CONFIGURATION_PRESENT, validation.readiness)
        unsupported = ReasoningCapability("unknown", "model", "Unknown", True, True, True)
        self.assertEqual(CapabilityReadiness.UNSUPPORTED, validate_reasoning_capability(unsupported).readiness)

    def test_observation_is_deterministic_evidence_linked_and_read_only(self) -> None:
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment=self.environment)
        context = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=capability, environment=self.environment, run_id="run-001")
        before = {path.relative_to(self.repository).as_posix(): path.read_bytes() for path in self.repository.rglob("*") if path.is_file()}
        events = []
        def record(event):
            if event.event_type == "repository-fingerprint-started":
                self.assertFalse((Path(workspace.workspace_path) / "onboarding-runs" / "run-001" / "observation.json").exists())
            events.append(event)
        result = observe_organization(context, progress_callback=record)
        after = {path.relative_to(self.repository).as_posix(): path.read_bytes() for path in self.repository.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(ObservationMode.READ_ONLY, result.context.observation_mode)
        self.assertEqual(result.discovery_feed, tuple(events))
        self.assertTrue(any(event.event_type == "repository-discovered" for event in result.discovery_feed))
        self.assertTrue(any(event.event_type == "architecture-signals-detected" for event in result.discovery_feed))
        self.assertLess(
            next(index for index, item in enumerate(events) if item.event_type == "repository-fingerprint-started"),
            next(index for index, item in enumerate(events) if item.event_type == "repository-observation-completed"),
        )
        self.assertTrue(any(event.event_type == "repository-fingerprint-progress" and event.processed_entries > 0 for event in result.discovery_feed))
        self.assertTrue(all(item.observation_ids for item in result.summary.observed))
        states = {item.name: item.state for item in result.understanding_meter.dimensions}
        self.assertEqual(UnderstandingState.OBSERVED, states["Repositories"])
        self.assertEqual(UnderstandingState.SIGNALS_DETECTED, states["Products"])
        self.assertTrue((Path(workspace.workspace_path) / "onboarding-runs" / "run-001" / "observation.json").is_file())
        self.assertFalse(any(path.is_relative_to(self.repository) for path in Path(workspace.workspace_path).rglob("*")))

    def test_repeated_runs_are_deterministic_and_observation_mode_rejects_writes(self) -> None:
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment=self.environment)
        first_context = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=capability, environment=self.environment)
        first = observe_organization(first_context)
        with self.assertRaisesRegex(ValueError, "already complete"):
            observe_organization(first_context)
        second_context = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=capability, environment=self.environment)
        second = observe_organization(second_context)
        self.assertEqual(first.repository_fingerprint, second.repository_fingerprint)
        self.assertEqual(first.discovery_feed, second.discovery_feed)
        self.assertEqual(first.understanding_meter, second.understanding_meter)
        self.assertEqual(first.summary, second.summary)
        self.assertEqual(
            tuple((item.event_type, item.message, item.processed_entries, item.evidence_paths) for item in first.discovery_feed),
            tuple((item.event_type, item.message, item.processed_entries, item.evidence_paths) for item in second.discovery_feed),
        )
        with self.assertRaisesRegex(ValueError, "read-only"):
            OrganizationContext(
                "acme-org",
                "run-003",
                str(self.repository),
                workspace.workspace_path,
                "write",  # type: ignore[arg-type]
                capability,
            )

    def test_restart_isolated_runs_and_no_unauthorized_workspace_overlap(self) -> None:
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment=self.environment)
        first = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=capability, environment=self.environment)
        observe_organization(first)
        second = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=capability, environment=self.environment)
        self.assertEqual("run-001", first.onboarding_run_id)
        self.assertEqual("run-002", second.onboarding_run_id)
        self.assertTrue((Path(workspace.workspace_path) / "onboarding-runs" / "run-001" / "observation.json").is_file())
        audit = json.loads((Path(workspace.workspace_path) / "audit" / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(list(range(len(audit))), [item["sequence"] for item in audit])
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            create_organization_workspace(
                self.repository / "workspace",
                organization_id="inside-org",
                display_name="Inside",
                repository_path=self.repository,
            )

    def test_organization_identity_isolated_and_unconfigured_provider_is_rejected(self) -> None:
        first = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        second = create_organization_workspace(self.base / "workspaces", organization_id="beta-org", display_name="Beta Organization", repository_path=self.repository)
        self.assertNotEqual(first.workspace_path, second.workspace_path)
        capability = recommend_reasoning_capability(environment={})
        with self.assertRaisesRegex(ValueError, "not locally configured"):
            restart_onboarding_run(first, repository_path=self.repository, reasoning_capability=capability, environment={})
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            restart_onboarding_run(second, repository_path=self.base / "workspaces", reasoning_capability=recommend_reasoning_capability(environment=self.environment), environment=self.environment)

    def test_misleading_metadata_remains_signal_not_mission_or_authority(self) -> None:
        (self.repository / "mission-notes.md").write_text("unverified filename", encoding="utf-8")
        (self.repository / "governance-draft.txt").write_text("unapproved draft", encoding="utf-8")
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        context = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=recommend_reasoning_capability(environment=self.environment), environment=self.environment)
        result = observe_organization(context)
        dimensions = {item.name: item for item in result.understanding_meter.dimensions}
        self.assertEqual(UnderstandingState.SIGNALS_DETECTED, dimensions["Mission"].state)
        self.assertEqual(UnderstandingState.SIGNALS_DETECTED, dimensions["Authority"].state)
        self.assertIn("requires customer confirmation", dimensions["Mission"].explanation)
        self.assertIn("requires customer confirmation", dimensions["Authority"].explanation)
        self.assertTrue(any("organizational mission requires customer confirmation" in item.statement for item in result.summary.requires_confirmation))

    def test_architecture_document_is_present(self) -> None:
        document = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "RIP-6.0-Trust-First-Organization-Onboarding-Architecture.md"
        self.assertTrue(document.is_file())
        self.assertIn("Observe First, Ask Second, Propose Third, Activate Last", document.read_text(encoding="utf-8"))
        guided_document = document.with_name("RIP-6.0-Phase-6B-Guided-Organizational-Understanding.md")
        self.assertTrue(guided_document.is_file())
        self.assertIn("Non-promotion Rule", guided_document.read_text(encoding="utf-8"))
        proposal_document = document.with_name("RIP-6.0-Phase-6C-Evidence-Based-Organizational-Understanding-Proposal.md")
        self.assertTrue(proposal_document.is_file())
        self.assertIn("Experience Layer", proposal_document.read_text(encoding="utf-8"))

    def _observed_run(self, *, add_governance_signal: bool = False):
        if add_governance_signal:
            (self.repository / "governance-notes.md").write_text("metadata only", encoding="utf-8")
        workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme Organization", repository_path=self.repository)
        context = restart_onboarding_run(workspace, repository_path=self.repository, reasoning_capability=recommend_reasoning_capability(environment=self.environment), environment=self.environment)
        return observe_organization(context)

    def test_guided_questions_are_deterministic_evidence_backed_and_prioritized(self) -> None:
        observation = self._observed_run()
        first = generate_guided_questions(observation)
        second = generate_guided_questions(observation)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len({item.resolution_key for item in first}))
        self.assertEqual(GuidedQuestionType.IDENTIFY_AUTHORITY, first[0].question_type)
        self.assertEqual(GuidedQuestionPriority.CRITICAL, first[0].priority)
        for question in first:
            self.assertTrue(question.observed)
            self.assertTrue(question.why_this_question)
            self.assertTrue(question.uncertainty_resolved)
            self.assertTrue(question.understanding_change)
            self.assertTrue(question.fingerprint)

    def test_guided_answer_history_is_immutable_resumeable_and_not_authority(self) -> None:
        observation = self._observed_run()
        state = begin_guided_understanding(observation)
        authority = next(item for item in state.questions if item.dimension == "Authority")
        answered = record_guided_answer(observation, state, question_id=authority.question_id, respondent_identity="Pat", respondent_role="Engineer", authority_claim="claimed organizational participant", disposition=GuidedAnswerDisposition.ANSWERED, answer="The board maintains governance records.")
        amended = record_guided_answer(observation, answered, question_id=authority.question_id, respondent_identity="Pat", respondent_role="Engineer", authority_claim="claimed organizational participant", disposition=GuidedAnswerDisposition.ANSWERED, answer="The board maintains the current governance records.")
        self.assertEqual(2, len(amended.answer_history))
        self.assertEqual(amended.answer_history[0].answer_id, amended.answer_history[1].supersedes_answer_id)
        resumed = begin_guided_understanding(observation)
        self.assertEqual(amended, resumed)
        self.assertIn("supplied", amended.questions[0].understanding_change)
        self.assertFalse((Path(observation.context.workspace_path) / "organizational-memory").exists())

    def test_contradictions_authority_gaps_and_source_changes_are_explicit(self) -> None:
        observation = self._observed_run()
        state = begin_guided_understanding(observation)
        authority = next(item for item in state.questions if item.dimension == "Authority")
        self.assertGreater(state.summary.authority_gaps, 0)
        first = record_guided_answer(observation, state, question_id=authority.question_id, respondent_identity="Pat", respondent_role="Executive", authority_claim="claimed", disposition=GuidedAnswerDisposition.ANSWERED, answer="Board")
        conflicting = record_guided_answer(observation, first, question_id=authority.question_id, respondent_identity="Lee", respondent_role="Executive", authority_claim="claimed", disposition=GuidedAnswerDisposition.ANSWERED, answer="Founder")
        self.assertGreater(conflicting.summary.contradictions, 0)
        self.assertTrue(any(item.question_type is GuidedQuestionType.RESOLVE_CONTRADICTION for item in conflicting.questions))
        (self.repository / "changed-after-observation.txt").write_text("change", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            begin_guided_understanding(observation)
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            record_guided_answer(observation, conflicting, question_id=authority.question_id, respondent_identity="New", respondent_role="", authority_claim="claimed", disposition=GuidedAnswerDisposition.ANSWERED, answer="Board")

    def test_guided_understanding_never_modifies_customer_repository(self) -> None:
        observation = self._observed_run()
        before = {path.relative_to(self.repository).as_posix(): path.read_bytes() for path in self.repository.rglob("*") if path.is_file()}
        state = begin_guided_understanding(observation)
        question = state.questions[0]
        record_guided_answer(observation, state, question_id=question.question_id, respondent_identity="Pat", respondent_role="", authority_claim="unknown", disposition=GuidedAnswerDisposition.UNKNOWN)
        after = {path.relative_to(self.repository).as_posix(): path.read_bytes() for path in self.repository.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_understanding_proposal_is_deterministic_provenance_backed_and_non_authoritative(self) -> None:
        observation = self._observed_run()
        state = begin_guided_understanding(observation)
        first = generate_understanding_proposal(observation, state, generated_at="audit-one")
        second = generate_understanding_proposal(observation, state, generated_at="audit-two")
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.proposal_fingerprint, second.proposal_fingerprint)
        self.assertNotEqual(first.generated_at, second.generated_at)
        self.assertEqual(ProposalReadiness.HUMAN_REVIEW_REQUIRED, first.readiness)
        self.assertTrue(first.authority_gaps)
        self.assertTrue(all(statement.provenance for section in first.sections for statement in section.statements))
        self.assertTrue(all(section.statements for section in first.sections))
        self.assertTrue(any(statement.statement_type is ProposedStatementType.OUTSTANDING_UNKNOWN for section in first.sections for statement in section.statements))
        self.assertFalse((Path(observation.context.workspace_path) / "organizational-memory").exists())

    def test_confirmations_withdrawals_and_stale_sources_preserve_boundaries(self) -> None:
        observation = self._observed_run(add_governance_signal=True)
        state = begin_guided_understanding(observation)
        authority = next(item for item in state.questions if item.dimension == "Authority")
        answered = record_guided_answer(observation, state, question_id=authority.question_id, respondent_identity="Pat", respondent_role="Owner", authority_claim="accepted onboarding authority", disposition=GuidedAnswerDisposition.ANSWERED, answer="The owner maintains current governance.")
        record = answered.answer_history[-1]
        interpretation = confirm_interpretation(observation, answered, question_id=authority.question_id, answer_ids=(record.answer_id,), statement_text="The owner is the supplied governance contact.", authority_category="onboarding-owner", authority_accepted=True)
        proposal = generate_understanding_proposal(observation, answered, confirmed_interpretations=(interpretation,))
        self.assertIn(interpretation.interpretation_id, proposal.supporting_interpretation_ids)
        withdrawal = withdraw_record(organization_id=observation.context.organization_id, onboarding_run_id=observation.context.onboarding_run_id, target_id=record.answer_id, target_type="answer", respondent_identity="Pat", reason="superseded supplied answer", source_fingerprint=observation.repository_fingerprint)
        withdrawn = generate_understanding_proposal(observation, answered, withdrawals=(withdrawal,))
        self.assertNotIn(record.answer_id, withdrawn.supporting_answer_ids)
        (self.repository / "changed.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            generate_understanding_proposal(observation, answered)

    def test_untrusted_confirmation_and_withdrawal_are_rejected_and_review_is_immutable(self) -> None:
        observation = self._observed_run(add_governance_signal=True)
        state = begin_guided_understanding(observation)
        authority = next(item for item in state.questions if item.dimension == "Authority")
        state = record_guided_answer(observation, state, question_id=authority.question_id, respondent_identity="Pat", respondent_role="Owner", authority_claim="accepted", disposition=GuidedAnswerDisposition.ANSWERED, answer="Owner")
        answer = state.answer_history[-1]
        interpretation = confirm_interpretation(observation, state, question_id=authority.question_id, answer_ids=(answer.answer_id,), statement_text="Owner supplied governance contact.", authority_category="owner", authority_accepted=True)
        with self.assertRaisesRegex(ValueError, "provenance"):
            generate_understanding_proposal(observation, state, confirmed_interpretations=(replace(interpretation, question_fingerprint="0" * 64),))
        invalid_withdrawal = withdraw_record(organization_id=observation.context.organization_id, onboarding_run_id=observation.context.onboarding_run_id, target_id="missing", target_type="answer", respondent_identity="Pat", reason="invalid", source_fingerprint=observation.repository_fingerprint)
        with self.assertRaisesRegex(ValueError, "withdrawal target"):
            generate_understanding_proposal(observation, state, withdrawals=(invalid_withdrawal,))
        proposal = generate_understanding_proposal(observation, state, confirmed_interpretations=(interpretation,))
        reviewed = review_understanding_proposal(observation, proposal)
        proposals = Path(observation.context.workspace_path) / "onboarding-runs" / observation.context.onboarding_run_id / "proposals"
        self.assertTrue((proposals / (proposal.proposal_id + ".json")).is_file())
        self.assertTrue((proposals / (proposal.proposal_id + ".reviewed.json")).is_file())
        self.assertNotEqual(proposal.proposal_status, reviewed.proposal_status)


if __name__ == "__main__":
    unittest.main()
    begin_guided_understanding,
    generate_guided_questions,
    record_guided_answer,

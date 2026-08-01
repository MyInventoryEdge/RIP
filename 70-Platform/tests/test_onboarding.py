from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.onboarding import (
    CapabilityReadiness,
    ObservationMode,
    OrganizationContext,
    ReasoningCapability,
    UnderstandingState,
    create_organization_workspace,
    observe_organization,
    recommend_reasoning_capability,
    restart_onboarding_run,
    validate_reasoning_capability,
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


if __name__ == "__main__":
    unittest.main()

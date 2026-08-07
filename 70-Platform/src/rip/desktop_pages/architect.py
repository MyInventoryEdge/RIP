"""Read-only constitutional Architect guidance over Repository Memory."""
from __future__ import annotations
from dataclasses import dataclass
from .repository_memory import RepositoryMemory

@dataclass(frozen=True, slots=True)
class EngineeringRecommendation:
    mission: str; reason: str; evidence: tuple[str,...]; expected_benefit: str; architectural_impact: str; acceptance: tuple[str,...]; risk: str; estimated_scope: str

@dataclass(frozen=True, slots=True)
class DebtItem:
    description: str; evidence: tuple[str,...]; customer_impact: str; architectural_impact: str; priority: str; status: str; resolved_date: str

def recommend(memory: RepositoryMemory) -> EngineeringRecommendation:
    if memory.observation_count < 2:
        return EngineeringRecommendation("Establish a second retained observation.", "Repository evolution is not yet observed from a single retained observation.", ("Repository timeline", "Observation count: 1"), "Enables evidence-backed evolution and growth answers.", "Extends Repository Memory history without changing constitutional evidence.", ("Complete a new governed observation.", "Repository Memory shows observation count greater than one.", "Repository Intelligence answers the evolution question from retained manifests."), "Low — observation remains read-only.", "One governed observation workflow.")
    return EngineeringRecommendation("Review retained repository evolution.", "Multiple retained observations are available.", ("Repository timeline", "Retained source manifests"), "Turns retained history into reviewable engineering context.", "No authority or repository modification.", ("Compare retained observations.",), "Low.", "Operator review.")

def debt_ledger(memory: RepositoryMemory) -> tuple[DebtItem,...]:
    if memory.observation_count < 2:
        return (DebtItem("Repository evolution coverage is incomplete.", ("Repository timeline contains one observation.",), "Change trends cannot yet be answered.", "Repository Memory has no comparative history.", "High", "Open", "Not resolved."),)
    return ()

def render_architect(memory: RepositoryMemory) -> str:
    r=recommend(memory); debt=debt_ledger(memory)
    debt_lines = tuple(f"• {d.description} Priority: {d.priority}; Status: {d.status}; Evidence: {'; '.join(d.evidence)}; Customer impact: {d.customer_impact}; Architectural impact: {d.architectural_impact}; Resolved date: {d.resolved_date}" for d in debt) or ("No retained debt items.",)
    return "\n".join(("Architect", "", "Current Product State", "Observed: Constitutional Foundation, Operator Workspace, Repository Memory, and Repository Intelligence are present in the installed platform.", "Derived: Repository evolution coverage is " + ("incomplete." if memory.observation_count < 2 else "available."), "Unknown: Self-onboarding readiness is not represented by retained Repository Memory evidence.", "", "Recommended Next Milestone", r.mission, "Reason: " + r.reason, "Evidence: " + "; ".join(r.evidence), "Expected Benefit: " + r.expected_benefit, "Architectural Impact: " + r.architectural_impact, "Risk: " + r.risk, "Estimated Scope: " + r.estimated_scope, "", "Technical Debt", *debt_lines, "", "Recently Completed", "Repository Intelligence is represented by retained Repository Memory capabilities.", "", "Engineering Assignments", "Objective: " + r.mission, "Affected areas: Retained observation workflow and Repository Memory timeline.", "Acceptance criteria: " + "; ".join(r.acceptance), "Verification plan: Run retained-observation, Repository Memory, and Repository Intelligence tests."))

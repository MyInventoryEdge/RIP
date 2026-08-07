"""Deterministic question engine over Repository Memory only."""
from __future__ import annotations

from dataclasses import dataclass

from .repository_memory import RepositoryMemory
from ..governed_memory import MemoryStore, retrieve


@dataclass(frozen=True, slots=True)
class IntelligenceAnswer:
    answer: str
    evidence: tuple[str, ...]
    confidence: str


def answer_question(memory: RepositoryMemory, question: str) -> IntelligenceAnswer:
    """Answer only facts represented by the supplied retained-evidence projection."""
    text = " ".join(question.casefold().split())
    if "what do you know about inventory edge" in text:
        records=MemoryStore().load("inventory-edge","inventory-edge")
        if not records: return IntelligenceAnswer("Observed: no governed Inventory Edge projection has been created from retained evidence.\nDerived: none.\nConfirmed: none.\nAuthoritative: none.\nUnknown: Inventory Edge evidence has not been retained in this namespace.", ("governed-memory namespace inventory-edge",), "Unknown")
        package=retrieve(records,organization_id="inventory-edge",repository_id="inventory-edge",scope="",query=question)
        lines=[]
        for status in ("Observed","Confirmed","Authoritative"):
            selected=[item.statement for item in package.selected if item.status==status]; lines.append(status+": "+("; ".join(selected) if selected else "none."))
        lines.extend(("Derived: none.","Unknown: coverage is limited to retained governed memory.",package.coverage_statement))
        return IntelligenceAnswer("\n".join(lines), tuple(e for item in package.selected for e in item.supporting_evidence), "High" if package.selected else "Unknown")
    if any(token in text for token in ("who is", "identity", "repository identity")):
        return IntelligenceAnswer(f"Repository: {memory.repository}\nRepository root: {memory.repository_root}", ("context.json",), "High")
    if any(token in text for token in ("major systems", "architecture", "systems exist")):
        return IntelligenceAnswer("Observed architecture areas: " + ", ".join(memory.observed_areas), ("final-source-manifest.json",), "High" if memory.observed_areas != ("Not yet observed.",) else "Unknown")
    if "capabilit" in text:
        return IntelligenceAnswer("Observed constitutional capabilities: " + ", ".join(memory.capabilities), ("retained observation, mutation, Trust, and Journal artifacts",), "High" if memory.capabilities != ("Not yet observed.",) else "Unknown")
    if any(token in text for token in ("runtime path", "expected to mutate", "runtime areas")):
        known = memory.runtime_areas
        return IntelligenceAnswer("Known runtime paths: " + ", ".join(known), ("integrity-difference.json",), "High" if known != ("Not yet observed.",) else "Unknown")
    if any(token in text for token in ("changed since", "evolution", "previous observation")):
        if memory.observation_count < 2:
            return IntelligenceAnswer("Not yet observed.", ("Repository timeline contains one retained observation.",), "Unknown")
        return IntelligenceAnswer(memory.growth, ("retained source manifests", "Repository timeline"), "Medium")
    if any(token in text for token in ("never observed", "not observed", "unknown areas")):
        return IntelligenceAnswer("Not yet observed: protected areas, stable architectural components, and repository evolution beyond the retained observation history.", ("Repository Memory completeness fields",), "Unknown")
    if any(token in text for token in ("latest decision", "governed decision", "trust action")):
        return IntelligenceAnswer("Latest governed decision: " + memory.latest_decision, ("trust-decision-envelope.json", "trust-execution-receipt.json"), "High" if memory.latest_decision != "Not yet observed." else "Unknown")
    return IntelligenceAnswer("Not yet observed.", ("No retained Repository Memory fact matches this question.",), "Unknown")


def render_answer(answer: IntelligenceAnswer) -> str:
    return "\n".join(("Answer", answer.answer, "", "Evidence", *answer.evidence, "", "Confidence", answer.confidence))

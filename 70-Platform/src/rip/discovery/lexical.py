"""Pure metadata-only lexical ranking for governed artifact discovery."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict

from ..foundation.models import Foundation
from ..observation.models import ObservationSet
from .eligibility import candidate_from_observation
from .models import ArtifactCandidate, ArtifactDiscoveryDiagnostics, ArtifactDiscoveryExclusion, ArtifactDiscoveryRanking, ArtifactDiscoveryReport, ArtifactDiscoveryResult, DiscoveryReason, fingerprint

DISCOVERY_VERSION = "1.0"
STRATEGY_NAME = "deterministic-artifact-lexical"
PHRASE_WEIGHT = 1_000
TITLE_WEIGHT = 30
FILENAME_WEIGHT = 20
ALIAS_WEIGHT = 15
DOCUMENT_ID_WEIGHT = 10
KIND_OR_EXTENSION_WEIGHT = 5
_PHRASE = re.compile(r'"([^"]+)"')
_TOKEN = re.compile(r"\w+", re.UNICODE)


def discover_artifacts(question: str, observations: ObservationSet, foundation: Foundation, *, candidate_limit: int, manual_inclusions: tuple[str, ...] = (), manual_exclusions: tuple[str, ...] = ()) -> ArtifactDiscoveryResult:
    if candidate_limit <= 0:
        raise ValueError("candidate limit must be positive")
    included = _normalize_paths(manual_inclusions)
    excluded = _normalize_paths(manual_exclusions)
    if set(included) & set(excluded):
        raise ValueError("manual inclusion and exclusion paths must not overlap")
    phrases, terms = _query_terms(question)
    candidates = tuple(candidate_from_observation(item, foundation) for item in observations.observations if item.kind not in {"directory", "repository_root", "access_error", "symbolic_link"})
    eligible = tuple(item for item in candidates if item.compatibility.value != "ineligible")
    exclusions = tuple(ArtifactDiscoveryExclusion(item, item.eligibility_reason) for item in candidates if item.compatibility.value == "ineligible")
    scored = [_score(item, phrases, terms) for item in eligible]
    scored.sort(key=lambda item: (-item.score, item.candidate.repository_relative_path.casefold(), item.candidate.observation_id))
    rankings = tuple(ArtifactDiscoveryRanking(item.candidate, index, item.score, item.reasons) for index, item in enumerate(scored))
    # Selection is deliberately deferred to Phase 5C; this contract records an empty selection.
    selected: tuple[ArtifactCandidate, ...] = ()
    diagnostics = ArtifactDiscoveryDiagnostics(len(candidates), len(eligible), len(exclusions), len(rankings), len(selected), bool(phrases or terms))
    payload = {
        "candidate_limit": candidate_limit,
        "discovery_version": DISCOVERY_VERSION,
        "manual_exclusions": excluded,
        "manual_inclusions": included,
        "question": question,
        "rankings": [asdict(item) for item in rankings],
        "selected_candidates": [asdict(item) for item in selected],
        "strategy": STRATEGY_NAME,
    }
    report = ArtifactDiscoveryReport(DISCOVERY_VERSION, STRATEGY_NAME, question, candidate_limit, included, excluded, candidates, exclusions, rankings, selected, fingerprint(payload), diagnostics)
    return ArtifactDiscoveryResult(selected, report)


class _Scored:
    def __init__(self, candidate: ArtifactCandidate, score: int, reasons: tuple[DiscoveryReason, ...]) -> None:
        self.candidate, self.score, self.reasons = candidate, score, reasons


def _score(candidate: ArtifactCandidate, phrases: tuple[str, ...], terms: tuple[str, ...]) -> _Scored:
    filename = candidate.repository_relative_path.rsplit("/", 1)[-1]
    parent_path = candidate.repository_relative_path.rsplit("/", 1)[0] if "/" in candidate.repository_relative_path else ""
    fields = (("filename", filename, FILENAME_WEIGHT), ("path", parent_path, FILENAME_WEIGHT), ("alias", " ".join(candidate.aliases), ALIAS_WEIGHT), ("governed-title", candidate.governed_title or "", TITLE_WEIGHT), ("governed-id", candidate.governed_document_id or "", DOCUMENT_ID_WEIGHT), ("extension", candidate.extension, KIND_OR_EXTENSION_WEIGHT), ("observed-kind", candidate.observed_kind, KIND_OR_EXTENSION_WEIGHT))
    reasons: list[DiscoveryReason] = []
    for signal, value, weight in fields:
        normalized = _normalize(value)
        phrase_matches = tuple(phrase for phrase in phrases if phrase in normalized)
        term_matches = tuple(term for term in terms if term in _TOKEN.findall(normalized))
        if phrase_matches:
            reasons.append(DiscoveryReason(f"{signal}-phrase", phrase_matches, PHRASE_WEIGHT, PHRASE_WEIGHT * len(phrase_matches)))
        if term_matches:
            reasons.append(DiscoveryReason(signal, term_matches, weight, weight * len(term_matches)))
    return _Scored(candidate, sum(item.contribution for item in reasons), tuple(reasons))


def _query_terms(question: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized = _normalize(question)
    phrases = tuple(dict.fromkeys(" ".join(match.group(1).split()) for match in _PHRASE.finditer(normalized) if _TOKEN.search(match.group(1))))
    remaining = _PHRASE.sub(" ", normalized)
    return phrases, tuple(dict.fromkeys(_TOKEN.findall(remaining)))


def _normalize_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(path.replace("\\", "/") for path in paths))
    if any(not path or path.startswith("/") or ".." in path.split("/") for path in normalized):
        raise ValueError("manual artifact paths must be repository-relative")
    return normalized


def _normalize(value: str) -> str:
    return re.sub(r"[_-]+", " ", unicodedata.normalize("NFKC", value).casefold())

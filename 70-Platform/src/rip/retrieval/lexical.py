"""Deterministic lexical ranking and budgeted selection of governed evidence chunks."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .canonical_session import UTF8_BYTES_PER_TOKEN
from .models import (
    ChunkCatalog,
    ChunkReference,
    CoverageStatus,
    CoverageSummary,
    EvidenceChunk,
    MessageRange,
    RankingEntry,
    RetrievalDiagnostics,
    RetrievalReport,
    RetrievalResult,
)

EXACT_PHRASE_WEIGHT = 1_000
TERM_WEIGHT = 10
IDENTIFIER_WEIGHT = 2
RETRIEVAL_VERSION = "1.0"
STRATEGY_NAME = "deterministic-lexical"
_QUOTED_PHRASE = re.compile(r'"([^"]+)"')
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class _QueryTerms:
    phrases: tuple[str, ...]
    terms: tuple[str, ...]

    @property
    def present(self) -> bool:
        return bool(self.phrases or self.terms)


class DeterministicLexicalRetrievalEngine:
    """Ranks canonical-session chunks without modifying, interpreting, or persisting them."""

    name = STRATEGY_NAME

    def retrieve(
        self,
        query: str,
        catalog: ChunkCatalog,
        *,
        token_budget: int,
        max_selected_chunks: int | None = None,
        surrounding_context: Literal["none"] = "none",
    ) -> RetrievalResult:
        if token_budget < 0:
            raise ValueError("retrieval token budget must be nonnegative")
        if max_selected_chunks is not None and max_selected_chunks <= 0:
            raise ValueError("maximum selected chunks must be positive when provided")
        if surrounding_context != "none":
            raise ValueError("Phase 3 supports only surrounding_context='none'")
        if catalog.descriptor.artifact_type != "canonical-session":
            raise ValueError("deterministic lexical retrieval requires a canonical-session catalog")

        terms = self._parse_query(query)
        scored = [self._score_chunk(chunk, terms) for chunk in catalog.chunks]
        scored.sort(key=lambda item: (-item.score, item.chunk.chunk_index, item.chunk.chunk_id))
        rankings = tuple(
            RankingEntry(ChunkReference.from_chunk(item.chunk), rank, item.score, item.reason)
            for rank, item in enumerate(scored)
        )
        selected_ranked: list[_ScoredChunk] = []
        token_usage = 0
        if terms.present:
            for item in scored:
                if item.score == 0:
                    continue
                estimated_tokens = self._estimate_tokens(item.chunk.content)
                if max_selected_chunks is not None and len(selected_ranked) >= max_selected_chunks:
                    continue
                if token_usage + estimated_tokens > token_budget:
                    continue
                selected_ranked.append(item)
                token_usage += estimated_tokens

        selected = tuple(sorted((item.chunk for item in selected_ranked), key=lambda chunk: chunk.chunk_index))
        selected_references = tuple(ChunkReference.from_chunk(chunk) for chunk in selected)
        selected_identities = {self._reference_identity(reference) for reference in selected_references}
        excluded_references = tuple(
            ChunkReference.from_chunk(chunk)
            for chunk in catalog.chunks
            if self._reference_identity(ChunkReference.from_chunk(chunk)) not in selected_identities
        )
        coverage = self._coverage(catalog, selected)
        fingerprint = self._fingerprint(query, rankings, selected_references, token_budget, max_selected_chunks, surrounding_context)
        report = RetrievalReport(
            retrieval_version=RETRIEVAL_VERSION,
            strategy=self.name,
            query=query,
            coverage=(coverage,),
            selected_chunks=selected_references,
            excluded_chunks=excluded_references,
            rankings=rankings,
            token_budget=token_budget,
            estimated_token_usage=token_usage,
            retrieval_fingerprint=fingerprint,
            diagnostics=RetrievalDiagnostics(
                chunks_considered=len(catalog.chunks),
                chunks_ranked=len(rankings),
                chunks_selected=len(selected),
                searchable_terms_present=terms.present,
            ),
        )
        return RetrievalResult(selected, report)

    @staticmethod
    def _parse_query(query: str) -> _QueryTerms:
        normalized = _normalize(query)
        phrases: list[str] = []
        for match in _QUOTED_PHRASE.finditer(normalized):
            phrase = " ".join(match.group(1).split())
            if phrase and _TOKEN.search(phrase) and phrase not in phrases:
                phrases.append(phrase)
        unquoted = _QUOTED_PHRASE.sub(" ", normalized)
        terms: list[str] = []
        for term in _TOKEN.findall(unquoted):
            if term not in terms:
                terms.append(term)
        return _QueryTerms(tuple(phrases), tuple(terms))

    def _score_chunk(self, chunk: EvidenceChunk, terms: _QueryTerms) -> "_ScoredChunk":
        messages = self._messages(chunk)
        phrase_matches = 0
        markdown_term_matches = 0
        identifier_term_matches = 0
        for message in messages:
            markdown = _normalize(message["markdown"])
            phrase_matches += sum(markdown.count(phrase) for phrase in terms.phrases)
            markdown_tokens = Counter(_TOKEN.findall(markdown))
            markdown_term_matches += sum(markdown_tokens[term] for term in terms.terms)
            identifiers = " ".join(str(message[field]) for field in ("source_message_id", "participant_id", "role"))
            identifier_tokens = Counter(_TOKEN.findall(_normalize(identifiers)))
            identifier_term_matches += sum(identifier_tokens[term] for term in terms.terms)
        score = (
            EXACT_PHRASE_WEIGHT * phrase_matches
            + TERM_WEIGHT * markdown_term_matches
            + IDENTIFIER_WEIGHT * identifier_term_matches
        )
        reason = (
            "no searchable lexical terms"
            if not terms.present
            else f"phrase_matches={phrase_matches}; markdown_term_matches={markdown_term_matches}; identifier_term_matches={identifier_term_matches}"
        )
        return _ScoredChunk(chunk, score, reason)

    @staticmethod
    def _messages(chunk: EvidenceChunk) -> list[dict[str, Any]]:
        if hashlib.sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.chunk_sha256:
            raise ValueError(f"chunk content hash does not match: {chunk.chunk_id}")
        try:
            messages = json.loads(chunk.content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"chunk content is not valid JSON: {chunk.chunk_id}") from exc
        if not isinstance(messages, list) or not all(isinstance(message, dict) for message in messages):
            raise ValueError(f"chunk content is not a message array: {chunk.chunk_id}")
        for message in messages:
            if not all(isinstance(message.get(field), str) for field in ("markdown", "source_message_id", "participant_id", "role")):
                raise ValueError(f"chunk message lacks canonical lexical fields: {chunk.chunk_id}")
        source_range = chunk.source_range
        if not isinstance(source_range, MessageRange):
            raise ValueError(f"chunk source range is not a MessageRange: {chunk.chunk_id}")
        if len(messages) != source_range.unit_count:
            raise ValueError(f"chunk message count does not match MessageRange: {chunk.chunk_id}")
        if messages[0]["source_message_id"] != source_range.start_message_id:
            raise ValueError(f"chunk starting message ID does not match MessageRange: {chunk.chunk_id}")
        if messages[-1]["source_message_id"] != source_range.end_message_id:
            raise ValueError(f"chunk ending message ID does not match MessageRange: {chunk.chunk_id}")
        source_orders = [message.get("source_order") for message in messages]
        if any(type(order) is not int for order in source_orders):
            raise ValueError(f"chunk source_order values must be integers: {chunk.chunk_id}")
        expected_orders = list(range(source_range.start_index, source_range.end_index + 1))
        if source_orders != expected_orders:
            raise ValueError(f"chunk source_order sequence does not match MessageRange: {chunk.chunk_id}")
        return messages

    @staticmethod
    def _estimate_tokens(content: str) -> int:
        return (len(content.encode("utf-8")) + UTF8_BYTES_PER_TOKEN - 1) // UTF8_BYTES_PER_TOKEN

    @staticmethod
    def _coverage(catalog: ChunkCatalog, selected: tuple[EvidenceChunk, ...]) -> CoverageSummary:
        represented = {
            index
            for chunk in selected
            for index in range(chunk.source_range.start_index, chunk.source_range.end_index + 1)
        }
        raw_units = sum(chunk.source_range.unit_count for chunk in selected)
        retrieved = len(represented)
        total = catalog.total_logical_units
        status = (
            CoverageStatus.COMPLETE if total > 0 and retrieved == total
            else CoverageStatus.PARTIAL if retrieved > 0
            else CoverageStatus.EMPTY
        )
        return CoverageSummary(
            repository_relative_path=catalog.descriptor.repository_relative_path,
            artifact_sha256=catalog.descriptor.sha256,
            total_logical_units=total,
            retrieved_logical_units=retrieved,
            omitted_logical_units=total - retrieved,
            overlap_logical_units=raw_units - retrieved,
            status=status,
        )

    @staticmethod
    def _fingerprint(
        query: str,
        rankings: tuple[RankingEntry, ...],
        selected: tuple[ChunkReference, ...],
        token_budget: int,
        max_selected_chunks: int | None,
        surrounding_context: str,
    ) -> str:
        payload = {
            "max_selected_chunks": max_selected_chunks,
            "query": query,
            "ranking_order": [asdict(entry) for entry in rankings],
            "retrieval_version": RETRIEVAL_VERSION,
            "selected_chunk_references": [asdict(reference) for reference in selected],
            "strategy": STRATEGY_NAME,
            "surrounding_context": surrounding_context,
            "token_budget": token_budget,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _reference_identity(reference: ChunkReference) -> tuple[str, str, str, str, int]:
        return (reference.repository_relative_path, reference.artifact_sha256, reference.chunk_sha256, reference.chunk_id, reference.chunk_index)


@dataclass(frozen=True, slots=True)
class _ScoredChunk:
    chunk: EvidenceChunk
    score: int
    reason: str


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()

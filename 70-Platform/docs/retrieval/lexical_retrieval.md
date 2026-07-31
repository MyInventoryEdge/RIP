# Deterministic Lexical Retrieval

Phase 3 ranks existing governed Canonical Session chunks. It does not alter chunks, infer
meaning, recommend conclusions, assign authority, call providers, or persist indexes.

The caller supplies an explicit nonnegative token budget. The engine uses no hidden budget
or configuration. For each request it normalizes text only for scoring with Unicode NFKC and
case folding. Quoted phrases are scored only against message Markdown. Unquoted unique terms
are scored against Markdown and stable message identifiers (`source_message_id`,
`participant_id`, and `role`). Arbitrary source metadata is retained in chunk content but is
not scored by this strategy.

Scores are deterministic integers:

- exact quoted-phrase occurrence in Markdown: 1,000;
- Markdown term occurrence: 10; and
- stable identifier term occurrence: 2.

All chunks receive a ranking entry. Ties resolve by chunk index, then chunk ID. Eligible
positive-score chunks are considered in ranking order and selected only when their complete,
unchanged content fits the remaining budget. Output chunks are then ordered chronologically.
No surrounding context is added in Phase 3.

The report records rankings, selections, exclusions, provenance, coverage, deterministic
diagnostic counts, budget use, and a SHA-256 retrieval fingerprint. The fingerprint represents
the query, strategy/version, ranking order, selected references, budget, and selection
settings; it is not an artifact hash, confidence score, or reasoning result.

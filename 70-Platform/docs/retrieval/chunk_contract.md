# RIP Chunk Contract

**Chunk-contract version:** `1.0`

## Purpose

Chunking represents oversized artifacts as bounded, deterministic, provenance-preserving
evidence units. It must not change source meaning or source content. Chunking is a
precondition for retrieval, not retrieval, reasoning, or interpretation.

## Required chunk invariants

Every valid chunk must:

- belong to exactly one `ArtifactDescriptor`;
- retain its repository-relative source path, source observation ID, and full artifact
  SHA-256 through its catalog provenance;
- have a deterministic chunk SHA-256, stable chunk ID, and zero-based chunk index;
- preserve exact source order and contain only complete logical source units;
- retain explicit source-range metadata;
- remain independently traceable to the original artifact;
- serialize deterministically; and
- contain unmodified source content.

## Chunker guarantees

Every chunker must guarantee that:

- identical input and configuration produce identical chunks;
- indexes are contiguous, non-overlapping, and ordered;
- each logical source unit appears exactly once unless an explicit overlap policy says
  otherwise;
- ordered chunks can reconstruct the chunked source region losslessly;
- no source unit is silently omitted;
- no chunk crosses an invalid structural boundary;
- its size policy is explicit and deterministic;
- hashes use a documented canonical representation; and
- validation failures are explicit, never arbitrary slicing fallbacks.

## Prohibited behavior

A chunker must never summarize, paraphrase, rewrite, or normalize away meaningful
whitespace, Markdown, code, punctuation, timestamps, IDs, or fields. It must never split
a logical record unless the artifact-specific contract explicitly permits it; invent IDs,
timestamps, fields, or provenance; reorder, silently truncate, or silently omit records;
infer authority from a filename alone; scan unrelated repository content; perform
retrieval, ranking, reasoning, or provider calls; mutate its source artifact; or persist a
derived index without a separate governed decision.

## Artifact-specific boundaries

Artifact contracts define logical units, for example:

- canonical session JSON: complete message objects;
- generic JSON arrays: complete array members;
- Markdown: complete structural blocks;
- CSV: header plus complete rows;
- logs: complete records or events; and
- OCR/PDF: complete pages or text-block units with page provenance.

An artifact-specific contract may narrow these boundaries, but may not weaken provenance,
determinism, or losslessness.

## Size policy

Each chunker must declare a deterministic maximum estimated-token or byte target, a soft
target, and a hard ceiling. Complete logical units take precedence over an exact target. A
single logical unit exceeding the hard ceiling must be emitted intact when supported by the
artifact-specific contract or rejected with an explicit oversized-unit error; it must never
be silently split. Any overlap must be explicit, bounded, deterministic, and represented
in metadata.

Chunkers must not optimize solely for maximum size. They should produce the smallest
practical number of chunks consistent with safe reasoning budgets and semantic continuity.

Initial Canonical Session defaults are deliberately non-universal implementation defaults:

- soft target: approximately 24,000 estimated tokens;
- hard ceiling: approximately 32,000 estimated tokens;
- estimation: conservative UTF-8 byte-based estimation already used by RIP;
- boundary: do not split a message; and
- oversized message: return an explicit oversized-unit condition.

### Canonical Session canonical serialization

Canonical Session chunks serialize their complete message objects as one JSON array. JSON is
encoded as UTF-8 with `ensure_ascii=False`, lexicographically sorted object keys, compact
`,` and `:` separators, no added newline, and no non-standard numeric constants. This
changes only JSON presentation; all parsed message values, including string whitespace and
Markdown, remain unchanged. The chunk SHA-256 is the SHA-256 of those UTF-8 bytes. A chunk
ID contains the full artifact SHA-256, chunk index, chunk SHA-256, and a deterministic
digest of the version metadata.

## Reassembly requirement

Sorting chunks by `chunk_index` must restore source order. Concatenating their logical
units must reconstruct the original chunked region exactly. Every logical unit must be
accounted for once, except for declared overlap. Artifact-specific tests must prove this
reassembly.

## Coverage requirement

Every chunk catalog must make it possible to calculate total, chunked, omitted, and
overlapping logical-unit counts; byte or token coverage where practical; and whether
coverage is complete. No component may claim complete artifact coverage without
deterministic proof.

## Error behavior

Chunkers must fail explicitly for malformed artifact structure, provenance mismatch,
unstable or duplicate IDs, noncontiguous indexes, impossible source ranges, unsupported
oversized logical units, or inability to preserve losslessness. Each error must identify
the artifact and the failed invariant.

## Test requirements

Every artifact-specific chunker must test deterministic repeated output, stable hashes and
IDs, complete logical boundaries, unmodified source content, contiguous indexes, exact
reassembly, malformed-input rejection, oversized-unit behavior, empty and single-unit
artifacts, and boundaries around its soft target and hard ceiling.

## Relationship to retrieval

Chunking creates governed evidence units. Retrieval ranks and selects those units; it does
not change them. Chunkers do not answer questions. Retrieval may select any valid chunk
without artifact-specific reconstruction logic, and reasoning must be told when supplied
coverage is partial rather than complete.

## Versioning

Each chunker implementation must declare its chunk-contract version, chunker name,
chunker version, size-policy version, and canonical-serialization version. A change to
boundaries, IDs, hashes, or serialization requires an applicable version change.

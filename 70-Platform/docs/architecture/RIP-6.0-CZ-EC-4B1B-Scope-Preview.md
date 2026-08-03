# CZ-EC-4B1B Scope Preview

The preview service consumes only a retained source manifest. It uses the already validated exact-path or restricted glob contracts, never follows symlink targets, deterministically reports every matched entry through its fingerprint and kind counts, and displays at most 100 paths. Validation recomputes the preview and rejects a changed manifest or matched set. More than 10,000 matches exposes an explicit acknowledgment requirement for a later acceptance workflow.

# RIP Platform

Executable platform for the Repository Intelligence Platform.

## Milestone 0001 — Foundation

```powershell
rip status
rip self
rip lexicon Authority
```

## Milestone 0002 — Filesystem Observation

RIP can now record deterministic evidence about the structure of its own repository without claiming semantic interpretation.

```powershell
rip observe
rip observe --all
rip observe --json
```

The default observation target is the nearest ancestor containing `.git`, or both `00-Constitution` and `70-Platform`. A path may also be supplied explicitly:

```powershell
rip observe C:\RIP
```

The observer records stable IDs, paths, evidence kinds, timestamps, and basic file metadata. It excludes common generated/cache directories such as `.git`, `__pycache__`, `node_modules`, `bin`, and `obj`.

## Install or update

From `C:\RIP\70-Platform`:

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

No network access, AI provider, database, or non-standard Python dependency is required.

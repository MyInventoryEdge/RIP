# RIP Platform — Milestone 0001

RIP can load and inspect its own five governed constitutional artifacts.

## Location

Place this complete directory at:

```text
C:\RIP\70-Platform
```

The platform reads the authoritative files from:

```text
C:\RIP\00-Constitution
```

It does not copy or modify those files.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer

## Install

Open PowerShell and run:

```powershell
cd C:\RIP\70-Platform
py -m pip install -e .
```

## Verify

```powershell
py -m unittest discover -s tests -v
rip status
```

The legacy command alias also works:

```powershell
rip-foundation status
```

## Commands

```powershell
rip status
rip lexicon Authority
rip section constitution "Primary Object"
rip constitution
rip self
```

You may also run the local entry point:

```powershell
py .\run-rip.py status
```

RIP automatically locates `00-Constitution` when run from `C:\RIP` or any directory beneath it. An explicit path is supported when needed:

```powershell
rip --root C:\RIP\00-Constitution status
```

## Scope

This milestone provides deterministic file loading, Markdown parsing, an in-memory object model, a CLI, and automated tests. It uses only the Python standard library at runtime. It does not yet provide AI reasoning, autonomous discovery, a database, or a user interface.

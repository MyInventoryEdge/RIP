"""Fail-closed release checks for the sole RIP operator executable."""
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path
import pefile

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def requires_administrator(path: Path) -> bool:
    pe = pefile.PE(str(path))
    try:
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id != 24:  # RT_MANIFEST
                continue
            for name in entry.directory.entries:
                for language in name.directory.entries:
                    data = language.data.struct
                    if b"requireAdministrator" in pe.get_data(data.OffsetToData, data.Size):
                        return True
        return False
    finally:
        pe.close()

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--exe", type=Path, required=True); parser.add_argument("--installer", type=Path, required=True); parser.add_argument("--installed", type=Path, required=True); args=parser.parse_args()
    sources=[p for p in (Path("src").rglob("*.py")) if p.is_file()]
    if not args.exe.is_file() or any(p.stat().st_mtime > args.exe.stat().st_mtime for p in sources):
        raise SystemExit("stale build: included source is newer than RIP.exe")
    if not args.installer.is_file() or args.installer.stat().st_mtime < args.exe.stat().st_mtime:
        raise SystemExit("stale installer: installer was not built from the current RIP.exe")
    if not args.installed.is_file() or digest(args.installed) != digest(args.exe):
        raise SystemExit("installed hash differs from release RIP.exe")
    if not requires_administrator(args.exe) or not requires_administrator(args.installed):
        raise SystemExit("elevation contract missing: RIP.exe must embed requireAdministrator")
    print("RIP release verification passed: " + digest(args.exe))
    return 0
if __name__ == "__main__": raise SystemExit(main())

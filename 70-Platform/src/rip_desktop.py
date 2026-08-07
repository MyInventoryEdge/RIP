"""Package entry point for the RIP desktop application.

Keeping this launcher outside the ``rip`` package ensures PyInstaller starts
the package normally, so the shell's relative imports remain valid in a
frozen executable.
"""

from rip.desktop import main


if __name__ == "__main__":
    raise SystemExit(main())

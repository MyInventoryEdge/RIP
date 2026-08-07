# RIP Windows build

The build environment is owned by RIP at `C:\RIP\build-tools\python313`.
It uses Python 3.13.11, PyInstaller 6.21.0, and OpenAI 2.41.0 as pinned in
`build-requirements.txt`.

Build the application from this directory:

```powershell
& C:\RIP\build-tools\python313\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name RIP --distpath build-output\internal --workpath build-output\work --specpath . --icon assets\rip.ico --version-file packaging\rip-version-info.txt --manifest packaging\RIP.manifest --paths src src\rip_desktop.py
```

Compile the installer after Inno Setup 7 is installed at
`C:\RIP\build-tools\inno-setup`:

```powershell
& C:\RIP\build-tools\inno-setup\ISCC.exe packaging\RIP.iss

& C:\RIP\build-tools\python313\python.exe packaging\verify_release.py --exe build-output\internal\RIP.exe --installer C:\RIP\Releases\RIP-Setup-0.4.0.exe --installed "C:\Program Files\RIP\RIP.exe"
```

The installer only owns the program files, shortcuts, and uninstall registry
entry. It does not provision or delete RIP authoritative state.

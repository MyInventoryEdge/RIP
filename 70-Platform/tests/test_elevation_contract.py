from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

from rip import desktop
from rip.elevation import elevation_failure_reason


class ElevationContractTests(unittest.TestCase):
    def test_packaged_manifest_requires_administrator(self) -> None:
        manifest = Path(__file__).parents[1] / "packaging" / "RIP.manifest"
        root = ET.fromstring(manifest.read_text(encoding="utf-8"))
        level = root.find(".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
        self.assertIsNotNone(level)
        self.assertEqual("requireAdministrator", level.attrib["level"])

    def test_non_windows_or_unverified_token_fails_closed(self) -> None:
        with patch("rip.elevation.os.name", "posix"):
            self.assertIn("requires", elevation_failure_reason())

    def test_absent_elevation_shows_explanation_before_desktop_is_created(self) -> None:
        native = Mock()
        with patch("rip.desktop.elevation_failure_reason", return_value="RIP must run as Administrator."), patch.object(desktop, "ctypes", native), patch("rip.desktop._SingleInstance") as single, patch("rip.desktop.RipDesktop") as shell:
            self.assertEqual(1, desktop.main())
        native.windll.user32.MessageBoxW.assert_called_once()
        single.assert_not_called()
        shell.assert_not_called()


if __name__ == "__main__":
    unittest.main()

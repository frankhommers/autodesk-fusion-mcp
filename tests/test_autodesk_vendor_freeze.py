"""Freeze checks for vendored Autodesk template utilities."""

import hashlib
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_DIR = ROOT / "lib" / "fusionAddInUtils"
CANONICAL_DIR = ROOT / "third_party" / "autodesk_fusion_template" / "lib" / "fusionAddInUtils"

EXPECTED_SHA256 = {
    "__init__.py": "79fba9048f78cb179933c3862e3d75b62bec6a57e4edbdbcc5f963138d596d00",
    "event_utils.py": "f1b8653b54c4b558487e4d20bef8a9c890be407e2e6c73b98e9091516ad3dfd8",
    "general_utils.py": "7e205413a4f4bc0c469625df36874d36f9f266397922c9490e037115b6925b30",
}


def normalized_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


class AutodeskVendorFreezeTests(unittest.TestCase):
    """Protect vendored Autodesk template files from accidental drift."""

    def test_canonical_snapshot_hashes_match_expected_values(self):
        for name, expected_hash in EXPECTED_SHA256.items():
            with self.subTest(path=name):
                digest = hashlib.sha256(
                    normalized_text(CANONICAL_DIR / name).encode("utf-8")
                ).hexdigest()
                self.assertEqual(digest, expected_hash)

    def test_live_files_match_canonical_snapshot(self):
        for name in EXPECTED_SHA256:
            with self.subTest(path=name):
                self.assertEqual(
                    normalized_text(LIVE_DIR / name),
                    normalized_text(CANONICAL_DIR / name),
                )


if __name__ == "__main__":
    unittest.main()

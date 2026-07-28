"""Tests for MCP protocol version negotiation.

Regression cover for issue #1: the server answered "2025-03-26" to every
initialize request regardless of what the client asked for, which caused
clients speaking a newer revision to drop the connection.
"""

import json
import pathlib
import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

from lib.mcp_server import (
    DEFAULT_PROTOCOL_VERSION,
    MCP_PROTOCOL_VERSION,
    SERVER_INFO,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_protocol_version,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NegotiationTests(unittest.TestCase):
    def test_every_supported_version_is_echoed_back(self):
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            with self.subTest(version=version):
                self.assertEqual(negotiate_protocol_version(version), version)

    def test_current_spec_revision_is_honoured(self):
        self.assertEqual(negotiate_protocol_version("2025-11-25"), "2025-11-25")

    def test_original_revision_still_honoured(self):
        self.assertEqual(negotiate_protocol_version("2025-03-26"), "2025-03-26")

    def test_unknown_version_falls_back_to_preferred(self):
        self.assertEqual(negotiate_protocol_version("1999-01-01"), MCP_PROTOCOL_VERSION)

    def test_absent_version_falls_back_to_preferred(self):
        self.assertEqual(negotiate_protocol_version(None), MCP_PROTOCOL_VERSION)

    def test_non_string_version_falls_back_to_preferred(self):
        self.assertEqual(negotiate_protocol_version(20251125), MCP_PROTOCOL_VERSION)


class VersionTableTests(unittest.TestCase):
    def test_preferred_version_is_the_newest_supported(self):
        self.assertEqual(MCP_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS[0])

    def test_supported_versions_are_ordered_newest_first(self):
        self.assertEqual(
            list(SUPPORTED_PROTOCOL_VERSIONS),
            sorted(SUPPORTED_PROTOCOL_VERSIONS, reverse=True),
        )

    def test_header_fallback_is_the_pre_header_revision(self):
        # Clients predating 2025-06-18 send no MCP-Protocol-Version header;
        # the spec says to assume 2025-03-26 in that case.
        self.assertEqual(DEFAULT_PROTOCOL_VERSION, "2025-03-26")
        self.assertIn(DEFAULT_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS)


class VersionConsistencyTests(unittest.TestCase):
    """The add-in manifest and the MCP serverInfo must not drift apart."""

    def test_manifest_version_matches_server_info(self):
        manifest = json.loads(
            (ROOT / "AutodeskFusionMCP.manifest").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], SERVER_INFO["version"])


if __name__ == "__main__":
    unittest.main()

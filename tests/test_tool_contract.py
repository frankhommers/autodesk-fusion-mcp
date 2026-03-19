"""Verify the public MCP tool surface: operation names, field names, and
schema structure.  No reference to old / renamed identifiers and no
source-tree scanning tricks."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fusion_bridge import tool_surface
from lib.mcp_server import MCPServer


class ToolSurfaceTests(unittest.TestCase):
    """Tests that tool_surface exposes the expected public constants."""

    EXPECTED_OPERATIONS = {
        "execute_python",
        "capture_viewport",
        "fetch_api_documentation",
        "fetch_online_documentation",
        "fetch_design_guide",
        "save_script",
        "load_script",
        "list_scripts",
        "delete_script",
    }

    def test_all_expected_operations_present(self):
        self.assertEqual(set(tool_surface.TOOL_OPERATIONS), self.EXPECTED_OPERATIONS)

    def test_operation_descriptions_are_nonempty(self):
        for name, desc in tool_surface.TOOL_OPERATIONS.items():
            with self.subTest(operation=name):
                self.assertIsInstance(desc, str)
                self.assertTrue(len(desc) > 5, f"Description too short for {name}")


class ToolSchemaTests(unittest.TestCase):
    """Tests that tool_input_schema contains required fields."""

    REQUIRED_FIELDS = {
        "operation",
        "api_path",
        "args",
        "kwargs",
        "remember_as",
        "return_properties",
        "code",
        "description",
        "session_id",
        "persistent",
        "search_term",
        "category",
        "max_results",
        "class_name",
        "member_name",
        "filename",
        "width",
        "height",
    }

    def setUp(self):
        self.schema = tool_surface.tool_input_schema()

    def test_schema_is_object_type(self):
        self.assertEqual(self.schema["type"], "object")

    def test_all_expected_fields_present(self):
        actual = set(self.schema["properties"].keys())
        missing = self.REQUIRED_FIELDS - actual
        self.assertFalse(missing, f"Missing schema fields: {missing}")

    def test_remember_as_field_exists(self):
        self.assertIn("remember_as", self.schema["properties"])

    def test_operation_field_lists_all_operations(self):
        op_desc = self.schema["properties"]["operation"]["description"]
        for name in ToolSurfaceTests.EXPECTED_OPERATIONS:
            self.assertIn(name, op_desc)


class ToolDescriptionTests(unittest.TestCase):
    """Tests that tool_description() contains expected content."""

    def setUp(self):
        self.description = tool_surface.tool_description()

    def test_mentions_remember_as(self):
        self.assertIn("remember_as", self.description)

    def test_mentions_all_operations(self):
        for name in ToolSurfaceTests.EXPECTED_OPERATIONS:
            self.assertIn(name, self.description)

    def test_mentions_path_shortcuts(self):
        for shortcut in ("app", "ui", "design", "rootComponent"):
            self.assertIn(shortcut, self.description)


class ServerSchemaTests(unittest.TestCase):
    """Tests that MCPServer picks up the correct schema by default."""

    def test_server_schema_matches_tool_surface(self):
        server = MCPServer()
        schema = server.tool_input_schema
        self.assertIn("remember_as", schema["properties"])
        op_desc = schema["properties"]["operation"]["description"]
        for name in ToolSurfaceTests.EXPECTED_OPERATIONS:
            self.assertIn(name, op_desc)


class ResourceTests(unittest.TestCase):
    """Tests that resource constants are defined."""

    def test_resource_uri(self):
        self.assertTrue(tool_surface.RESOURCE_URI.startswith("fusion://"))

    def test_resource_name_nonempty(self):
        self.assertTrue(len(tool_surface.RESOURCE_NAME) > 0)


if __name__ == "__main__":
    unittest.main()

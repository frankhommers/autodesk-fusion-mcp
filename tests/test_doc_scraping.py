"""Tests for the Autodesk cloudhelp HTML scraping in ``doc_lookup``.

These pin the assumptions we make about Autodesk's help markup.  Autodesk
changes that markup without notice -- in 2025 the emphasis tag around the
member name in the syntax line switched from ``<strong>`` to ``<b>``, which
silently dropped the ``syntax`` field from every lookup.
"""

import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

from fusion_bridge.doc_lookup import DocumentationProvider


def _page(body, paragraph='<p class="api">Creates a new sketch.</p>'):
    """Wrap *body* in a minimal cloudhelp-shaped document.

    The default paragraph mirrors the live markup, which carries a class
    attribute -- matching a bare ``<p>`` silently yielded no description.
    """
    return (
        '<html><body><h2 class="api">Description</h2>'
        + paragraph
        + "<pre>"
        + body
        + "</pre></body></html>"
    )


class SyntaxExtractionTests(unittest.TestCase):
    def setUp(self):
        self.provider = DocumentationProvider()

    def _syntax(self, html):
        result = self.provider._extract_all_sections(
            html, "https://example.invalid", "Sketches", "add"
        )
        return result.get("syntax")

    def test_bold_tag_is_current_autodesk_layout(self):
        html = _page("returnValue = sketches_var.<b>add</b>(planarEntity)")
        self.assertEqual(self._syntax(html), "add(planarEntity)")

    def test_strong_tag_legacy_layout_still_supported(self):
        html = _page("returnValue = sketches_var.<strong>add</strong>(planarEntity)")
        self.assertEqual(self._syntax(html), "add(planarEntity)")

    def test_multiple_arguments_are_captured(self):
        html = _page(
            "returnValue = sketches_var.<b>add</b>(planarEntity, occurrenceForCreation)"
        )
        self.assertEqual(self._syntax(html), "add(planarEntity, occurrenceForCreation)")

    def test_mismatched_tags_do_not_match(self):
        html = _page("returnValue = sketches_var.<b>add</strong>(planarEntity)")
        self.assertIsNone(self._syntax(html))

    def test_cpp_arrow_form_is_not_mistaken_for_python(self):
        html = _page("returnValue = sketches_var-&gt;<b>add</b>(planarEntity);")
        self.assertIsNone(self._syntax(html))

    def test_absent_syntax_line_omits_the_key(self):
        self.assertIsNone(self._syntax(_page("nothing useful here")))


class SectionExtractionTests(unittest.TestCase):
    """Guard the <h2>-driven section parsing we rely on."""

    def setUp(self):
        self.provider = DocumentationProvider()

    def test_description_with_class_attribute_is_parsed(self):
        # Live markup is <p class="api">; a bare <p> match returned nothing.
        result = self.provider._extract_all_sections(
            _page(""), "https://example.invalid", "Sketches", "add"
        )
        self.assertEqual(result["description"], "Creates a new sketch.")

    def test_description_without_attributes_is_parsed(self):
        result = self.provider._extract_all_sections(
            _page("", paragraph="<p>Creates a new sketch.</p>"),
            "https://example.invalid",
            "Sketches",
            "add",
        )
        self.assertEqual(result["description"], "Creates a new sketch.")

    def test_description_tags_are_stripped(self):
        result = self.provider._extract_all_sections(
            _page("", paragraph='<p class="api">Creates a <b>new</b> sketch.</p>'),
            "https://example.invalid",
            "Sketches",
            "add",
        )
        self.assertEqual(result["description"], "Creates a new sketch.")

    def test_identity_fields_are_passed_through(self):
        result = self.provider._extract_all_sections(
            _page(""), "https://example.invalid", "Sketches", "add"
        )
        self.assertEqual(result["url"], "https://example.invalid")
        self.assertEqual(result["class_name"], "Sketches")
        self.assertEqual(result["member_name"], "add")

    def test_missing_member_name_normalises_to_none(self):
        result = self.provider._extract_all_sections(
            _page(""), "https://example.invalid", "Sketches", ""
        )
        self.assertIsNone(result["member_name"])


def _sectioned(*sections):
    """Build a page from ``(heading, inner_html)`` pairs."""
    parts = ["<html><body>"]
    for heading, inner in sections:
        parts.append(f'<h2 class="api">{heading}</h2>{inner}')
    parts.append("</body></html>")
    return "".join(parts)


_MEMBER_TABLE = (
    "<table>"
    "<tr><th>Name</th><th>Description</th></tr>"
    "<tr><td>addByCurve</td><td>Adds a curve.</td></tr>"
    "<tr><td>deleteMe</td><td>Deletes the entity.</td></tr>"
    "</table>"
)


class PropertyPageTests(unittest.TestCase):
    """Property pages carry prose under 'Property Value', not a table."""

    def setUp(self):
        self.provider = DocumentationProvider()

    def _parse(self, html):
        return self.provider._extract_all_sections(
            html, "https://example.invalid", "Sketch", "profiles"
        )

    def test_read_only_property_is_described(self):
        result = self._parse(
            _sectioned(
                (
                    "Property Value",
                    "This is a read only property whose value is a "
                    '<a href="Profiles.htm">Profiles</a>.',
                )
            )
        )
        self.assertEqual(result["property_type"], "Profiles")
        self.assertEqual(result["access"], "read only")
        self.assertIn("read only", result["property_description"])

    def test_read_write_property_access_is_detected(self):
        result = self._parse(
            _sectioned(
                (
                    "Property Value",
                    "This is a read/write property whose value is a "
                    '<a href="DesignTypes.htm">DesignTypes</a>.',
                )
            )
        )
        self.assertEqual(result["property_type"], "DesignTypes")
        self.assertEqual(result["access"], "read/write")

    def test_property_syntax_survives_unclosed_bold_tag(self):
        # Autodesk emits "propertyValue = sketch_var.<b>profiles<br />" --
        # note the <b> is never closed.
        html = _sectioned(
            ("Syntax", "<pre>propertyValue = sketch_var.<b>profiles<br /></pre>")
        )
        self.assertEqual(self._parse(html)["syntax"], "profiles")

    def test_method_syntax_wins_over_property_syntax(self):
        html = _sectioned(
            (
                "Syntax",
                "<pre>returnValue = sketches_var.<b>add</b>(planarEntity)<br />"
                "propertyValue = sketches_var.<b>count</pre>",
            )
        )
        self.assertEqual(self._parse(html)["syntax"], "add(planarEntity)")


class ClassPageTests(unittest.TestCase):
    """Class pages list members in tables that were previously discarded."""

    def setUp(self):
        self.provider = DocumentationProvider()

    def _parse(self, html):
        return self.provider._extract_all_sections(
            html, "https://example.invalid", "Sketch", None
        )

    def test_methods_table_is_captured(self):
        result = self._parse(_sectioned(("Methods", _MEMBER_TABLE)))
        self.assertEqual(
            [m["name"] for m in result["methods"]], ["addByCurve", "deleteMe"]
        )
        self.assertEqual(result["methods"][0]["description"], "Adds a curve.")

    def test_properties_table_is_captured(self):
        result = self._parse(_sectioned(("Properties", _MEMBER_TABLE)))
        self.assertEqual(len(result["properties"]), 2)

    def test_accessed_from_links_are_listed(self):
        result = self._parse(
            _sectioned(
                (
                    "Accessed From",
                    '<a href="A.htm">A.one</a>, <a href="B.htm">B.two</a>',
                )
            )
        )
        self.assertEqual(result["accessed_from"], ["A.one", "B.two"])
        self.assertNotIn("accessed_from_truncated", result)

    def test_long_accessed_from_list_is_capped(self):
        links = ", ".join(f'<a href="C{i}.htm">C{i}.member</a>' for i in range(40))
        result = self._parse(_sectioned(("Accessed From", links)))
        self.assertEqual(len(result["accessed_from"]), 25)
        self.assertEqual(result["accessed_from_truncated"], 40)


class PreviewFlagTests(unittest.TestCase):
    """Preview classes get renamed without deprecation, so callers need this."""

    def setUp(self):
        self.provider = DocumentationProvider()

    def _preview(self, html):
        return self.provider._extract_all_sections(
            html, "https://example.invalid", "FoldFeature", None
        )["preview"]

    def test_api_preview_banner_is_detected(self):
        html = _sectioned(
            ("Description", '<p class="api-preview">This is in preview.</p>')
        )
        self.assertTrue(self._preview(html))

    def test_test_tube_icon_is_detected(self):
        html = (
            '<h1 class="api">FoldFeature Object '
            '<img src="../images/TestTubeLarge.png" alt="Preview"></h1>'
        ) + _sectioned(("Description", '<p class="api">A fold.</p>'))
        self.assertTrue(self._preview(html))

    def test_stable_page_is_not_flagged(self):
        html = _sectioned(("Description", '<p class="api">An extrude.</p>'))
        self.assertFalse(self._preview(html))

    def test_stable_class_containing_preview_members_is_not_flagged(self):
        # Sketch is stable but lists preview members, each carrying the same
        # test-tube icon in the member table. Scanning the whole page for the
        # icon marked Sketch itself as preview.
        html = (
            '<h1 class="api">Sketch Object</h1>'
            + _sectioned(
                (
                    "Methods",
                    "<table><tr><th>Name</th><th>Description</th></tr>"
                    '<tr><td>autoConstrain</td><td class="api-list">'
                    '<img src="../images/TestTubeSmall.png" alt="Preview">'
                    "Auto constrains the sketch.</td></tr></table>",
                )
            )
        )
        self.assertFalse(self._preview(html))

    def test_flag_is_always_present(self):
        result = self.provider._extract_all_sections(
            _page(""), "https://example.invalid", "Sketch", None
        )
        # Absence would be ambiguous: unset could mean "not preview" or
        # "parser did not look", so the key is always emitted.
        self.assertIn("preview", result)


class SamplesTests(unittest.TestCase):
    def setUp(self):
        self.provider = DocumentationProvider()

    def test_each_sample_gets_its_own_url(self):
        # Regression: the href was searched across the whole section, so every
        # sample row inherited the first row's link.
        html = _sectioned(
            (
                "Samples",
                "<table>"
                "<tr><th>Name</th><th>Description</th></tr>"
                '<tr><td><a href="first.htm">First</a></td><td>One.</td></tr>'
                '<tr><td><a href="second.htm">Second</a></td><td>Two.</td></tr>'
                "</table>",
            )
        )
        samples = self.provider._extract_all_sections(
            html, "https://example.invalid", "Sketch", None
        )["samples"]
        urls = [s["url"] for s in samples]
        self.assertEqual(len(set(urls)), 2)
        self.assertTrue(urls[0].endswith("/first.htm"))
        self.assertTrue(urls[1].endswith("/second.htm"))


if __name__ == "__main__":
    unittest.main()

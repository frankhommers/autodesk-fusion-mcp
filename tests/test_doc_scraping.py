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


if __name__ == "__main__":
    unittest.main()

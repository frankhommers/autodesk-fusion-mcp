"""Fusion API introspection, online docs, and bundled guide lookup.

The `DocumentationProvider` class encapsulates guide reading and HTML
scraping.  The `fetch_*` module-level functions delegate to a default
provider instance.
"""

import inspect
import json
import os
import re
import traceback
import urllib.error
import urllib.request
from types import FunctionType, ModuleType


# ── Response helpers ──────────────────────────────────────────────────────


def _ok(message):
    return {"content": [{"type": "text", "text": message}], "isError": False}


def _err(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


# ── Introspection utilities ──────────────────────────────────────────────


def member_signature(func):
    try:
        sig = str(inspect.signature(func))
        sig = sig.replace("(self, ", "(").replace("(self)", "()")
        sig = sig.replace("'", "").replace("::", ".")
        return re.sub(r"adsk\.core\.Ptr<([^>]+)>", r"\1", sig)
    except Exception:
        return None


def class_overview(cls, namespace_name):
    """Summarise a class.  Returns ``"members"`` list instead of separate
    ``"properties"`` / ``"functions"`` keys."""
    info = {
        "type": "class",
        "name": cls.__name__,
        "namespace": f"adsk.{namespace_name}",
        "doc": (cls.__doc__ or "")[:500],
    }
    members = []
    for attr_name, attr_val in cls.__dict__.items():
        if attr_name.startswith("_"):
            continue
        if isinstance(attr_val, property):
            members.append(
                {
                    "name": attr_name,
                    "kind": "property",
                    "doc": ((attr_val.__doc__ or "").split(".", 1)[0])[:200],
                }
            )
        elif isinstance(attr_val, FunctionType):
            members.append(
                {
                    "name": attr_name,
                    "kind": "function",
                    "doc": ((attr_val.__doc__ or "").split(".", 1)[0])[:200],
                }
            )
    if members:
        info["members"] = members[:20]
    return info


# ── Scored search helpers ────────────────────────────────────────────────

_SCORE_EXACT = 100
_SCORE_PARTIAL_NAME = 50
_SCORE_DOC_HIT = 20


def _score_hit(kind, namespace_name, cls, member_name, member_obj, query, category):
    """Return a relevance score for a single candidate, or 0 for no match."""
    best = 0

    if kind == "class":
        cls_lower = cls.__name__.lower()
        if category in ("class_name", "all"):
            if query == cls_lower:
                best = max(best, _SCORE_EXACT)
            elif query in cls_lower:
                best = max(best, _SCORE_PARTIAL_NAME)
        if category in ("description", "all"):
            if query in (cls.__doc__ or "").lower():
                best = max(best, _SCORE_DOC_HIT)
    else:
        ml = member_name.lower()
        if category in ("member_name", "all"):
            if query == ml:
                best = max(best, _SCORE_EXACT)
            elif query in ml:
                best = max(best, _SCORE_PARTIAL_NAME)
        if category in ("description", "all"):
            if query in (getattr(member_obj, "__doc__", "") or "").lower():
                best = max(best, _SCORE_DOC_HIT)

    return best


def _classify_hit(kind, namespace_name, cls, member_name, member_obj):
    """Convert a raw hit tuple into a display dict."""
    if kind == "class":
        return class_overview(cls, namespace_name)
    if isinstance(member_obj, property):
        entry = {
            "type": "property",
            "name": member_name,
            "class": cls.__name__,
            "namespace": f"adsk.{namespace_name}",
            "doc": (member_obj.__doc__ or "")[:500],
        }
        if member_obj.fset is None:
            entry["readonly"] = True
        return entry

    entry = {
        "type": "function",
        "name": member_name,
        "class": cls.__name__,
        "namespace": f"adsk.{namespace_name}",
        "doc": (member_obj.__doc__ or "")[:500],
    }
    sig = member_signature(member_obj)
    if sig:
        entry["signature"] = sig
    return entry


# ── DocumentationProvider ────────────────────────────────────────────────


class DocumentationProvider:
    """Encapsulates guide file path, HTML scraping, and introspection."""

    _AUTODESK_HELP = "https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files"

    def __init__(self, guide_path=None):
        if guide_path is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            guide_path = os.path.join(root, "guides", "fusion-design-guide.md")
        self._guide_path = guide_path

    # -- bundled guide -----------------------------------------------------

    def read_guide(self):
        with open(self._guide_path, "r", encoding="utf-8") as fh:
            return fh.read()

    def handle_design_guide(self, arguments, log_fn):
        del arguments
        log_fn("[MCP] Tool call: fetch_design_guide")
        try:
            text = self.read_guide()
            header = (
                f"Fusion Design Guide\n\nLength: {len(text.splitlines())} lines\n\n"
            )
            return _ok(header + text)
        except Exception as exc:
            return _err(f"ERROR reading design guide: {exc}")

    # -- introspection search (scored ranking) -----------------------------

    def handle_api_search(self, arguments, log_fn):
        term = arguments.get("search_term", "")
        category = arguments.get("category", "class_name")
        max_results = arguments.get("max_results", 3)

        log_fn(f"[MCP] Tool call: fetch_api_documentation - {term} ({category})")
        if not term:
            return _err("Missing required parameter 'search_term'")

        try:
            import adsk

            query = term.lower().strip()
            if query.startswith("adsk."):
                query = query[5:]

            ns_filter = None
            cls_filter = None
            if "." in query:
                ns_filter, _, query = query.partition(".")
                if "." in query:
                    cls_filter, _, query = query.partition(".")
            if category != "description":
                query = query.split()[0] if query else ""

            scored = []  # list of (score, hit_tuple)

            for ns_name, ns_mod in adsk.__dict__.items():
                if ns_name.startswith("_") or not isinstance(ns_mod, ModuleType):
                    continue
                if ns_filter and ns_name.lower() != ns_filter:
                    continue

                for cname, cobj in ns_mod.__dict__.items():
                    if cname.startswith("_") or not isinstance(cobj, type):
                        continue
                    if cls_filter and cname.lower() != cls_filter:
                        continue

                    # Score the class itself
                    if category in ("class_name", "description", "all"):
                        s = _score_hit(
                            "class", ns_name, cobj, None, None, query, category
                        )
                        if s:
                            scored.append((s, ("class", ns_name, cobj, None, None)))

                    # Score members
                    if category in ("member_name", "description", "all"):
                        for mname, mobj in cobj.__dict__.items():
                            if mname.startswith("_"):
                                continue
                            if not isinstance(mobj, (property, FunctionType)):
                                continue
                            s = _score_hit(
                                "member", ns_name, cobj, mname, mobj, query, category
                            )
                            if s:
                                scored.append(
                                    (s, ("member", ns_name, cobj, mname, mobj))
                                )

            scored.sort(key=lambda pair: pair[0], reverse=True)
            top = [_classify_hit(*hit) for _, hit in scored[:max_results]]

            if not top:
                return _ok(f"No results found for '{term}' in category '{category}'")
            return _ok(json.dumps(top, indent=2))

        except Exception as exc:
            return _err(
                f"ERROR searching documentation: {exc}\n{traceback.format_exc()}"
            )

    # -- online HTML docs (single-pass extraction) -------------------------

    def handle_online_docs(self, arguments, log_fn):
        class_name = arguments.get("class_name", "")
        member_name = arguments.get("member_name", "")

        if member_name:
            log_fn(
                f"[MCP] Tool call: fetch_online_documentation - {class_name}.{member_name}"
            )
        else:
            log_fn(f"[MCP] Tool call: fetch_online_documentation - {class_name}")

        if not class_name:
            return _err("ERROR: 'class_name' parameter required")

        fname = (
            f"{class_name}_{member_name}.htm" if member_name else f"{class_name}.htm"
        )
        url = f"{self._AUTODESK_HELP}/{fname}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FusionMCP/2"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")

            result = self._extract_all_sections(html, url, class_name, member_name)
            return _ok(json.dumps(result, indent=2))

        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                return _err(f"HTTP Error {exc.code}: {exc}")
            alternatives = []
            if not member_name:
                alternatives.append(
                    f"{class_name[:-1]}.htm"
                    if class_name.endswith("s")
                    else f"{class_name}s.htm"
                )
            payload = {
                "error": f"No documentation page at {url}",
                "suggestion": "Try a different class/member spelling",
                "alternatives_to_try": alternatives,
                "fallback": "Use fetch_api_documentation for introspection results",
            }
            return {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                "isError": True,
            }
        except Exception as exc:
            return _err(
                f"ERROR fetching documentation: {exc}\n{traceback.format_exc()}"
            )

    def _extract_all_sections(self, html, url, class_name, member_name):
        """Parse all relevant sections from the Autodesk help HTML in a
        single pass through the ``<h2>`` structure."""
        result = {
            "url": url,
            "class_name": class_name,
            "member_name": member_name or None,
        }

        # Split by <h2> to process sections generically
        sections = re.split(r"<h2[^>]*>", html)
        for raw_section in sections:
            heading_end = raw_section.find("</h2>")
            if heading_end == -1:
                continue
            heading = _strip_tags(raw_section[:heading_end]).strip().lower()
            body = raw_section[heading_end + 5 :]

            if heading == "description":
                m = re.search(r"<p>(.*?)</p>", body, re.DOTALL)
                if m:
                    result["description"] = _strip_tags(m.group(1))

            elif heading == "parameters":
                result["parameters"] = _extract_table_rows(
                    body, ("name", "type", "description")
                )

            elif heading == "return value":
                rows = _extract_table_rows(body, ("type", "description"))
                if rows:
                    result["return_type"] = rows[0].get("type", "")
                    result["return_description"] = rows[0].get("description", "")

            elif heading == "samples":
                samples = []
                for row in _extract_table_rows(body, ("name", "description")):
                    href = re.search(r'href="([^"]+)"', body)
                    if href:
                        row["url"] = f"{self._AUTODESK_HELP}/{href.group(1)}"
                    samples.append(row)
                if samples:
                    result["samples"] = samples

        # Syntax (outside h2 structure)
        syntax_m = re.search(
            r"returnValue\s*=\s*\w+\.<strong>(\w+)</strong>\((.*?)\)", html
        )
        if syntax_m:
            result["syntax"] = f"{syntax_m.group(1)}({syntax_m.group(2)})"

        return result


# ── HTML helpers ──────────────────────────────────────────────────────────


def _strip_tags(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _extract_table_rows(html_fragment, columns):
    """Pull table rows from *html_fragment* mapping cells to *columns*."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_fragment, re.DOTALL)
    out = []
    for row in rows[1:]:  # skip header row
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < len(columns):
            continue
        out.append({col: _strip_tags(cells[i]) for i, col in enumerate(columns)})
    return out


# ── Module-level default provider and backwards-compat exports ───────────

_provider = DocumentationProvider()

# Keep the same function signatures expected by operations.py
strip_tags = _strip_tags
get_guide_path = lambda: _provider._guide_path
read_design_guide = _provider.read_guide


def fetch_api_documentation(arguments, log_fn):
    return _provider.handle_api_search(arguments, log_fn)


def fetch_online_documentation(arguments, log_fn):
    return _provider.handle_online_docs(arguments, log_fn)


def fetch_design_guide(arguments, log_fn):
    return _provider.handle_design_guide(arguments, log_fn)

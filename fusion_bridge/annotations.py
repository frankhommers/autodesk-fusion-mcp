"""Selection annotations shared by the Fusion palette and MCP tools.

All entry points run on Fusion's main thread, serializing claims and UI edits.
Annotation text and state live only in memory. Captured objects get a Fusion
attribute ("marker") in MARKER_GROUP: Fusion carries it along when geometry is
recomputed or split, which in-memory references do not survive. Markers are
removed with their annotation, on completion and when the add-in stops.
"""

import json
import math
from uuid import uuid4

from .annotation_store import AnnotationStore
from .dispatch import get_app
from . import value_builders
from .selection import _safe_attr, _get_parent_component

STORE = AnnotationStore()
MARKER_GROUP = "autodesk-fusion-mcp"
_documents = {}
_capture = None


def clear():
    global _capture
    for item in STORE.items.values():
        _drop_references(item["id"])
        _unmark(item)
    STORE.clear()
    _documents.clear()
    _capture = None


def _drop_references(item_id):
    prefix = f"annotation_{item_id}_"
    for key in list(value_builders.OBJECT_STORE):
        if key.startswith(prefix):
            del value_builders.OBJECT_STORE[key]


def _document():
    global _capture
    # Closed documents and their object handles must not survive in the queue.
    for key, document in list(_documents.items()):
        if not document.isValid:
            # Markers of a closed document can only be purged after reopening it.
            for item_id, item in list(STORE.items.items()):
                if item["document"] == key:
                    _drop_references(item_id)
                    del STORE.items[item_id]
            if _capture and _capture["document"] == key:
                _capture = None
            del _documents[key]
    document = get_app().activeDocument
    if document is None:
        return None
    for key, existing in _documents.items():
        if existing == document:
            return key
    key = uuid4().hex
    _documents[key] = document
    return key


def _valid(entities):
    return all(_safe_attr(entity, "isValid") is True for entity in entities)


def _entity_info(entity):
    return dict(objectType=_safe_attr(entity, "objectType"),
                name=_safe_attr(entity, "name"),
                parentComponent=_get_parent_component(entity),
                entityToken=_safe_attr(entity, "entityToken"),
                valid=_safe_attr(entity, "isValid") is True)


def _design(document):
    try:
        return _documents[document].products.itemByProductType("DesignProductType")
    except Exception:
        return None


def _find_markers(design, name=""):
    try:
        return list(design.findAttributes(MARKER_GROUP, name) or [])
    except Exception:
        return []


def _rolled_back(design):
    # Entities after the timeline marker do not exist, so nothing can be verified.
    try:
        timeline = design.timeline
        return timeline.markerPosition < timeline.count
    except Exception:
        return False


def _fingerprint(entity):
    values = {}
    for name in ("area", "length", "volume"):
        value = _safe_attr(entity, name)
        if isinstance(value, (int, float)):
            values[name] = [value]
    box = _safe_attr(entity, "boundingBox")
    try:
        values["box"] = [getattr(point, axis) for point in (box.minPoint, box.maxPoint)
                         for axis in "xyz"]
    except Exception:
        pass
    return values


def _same_shape(before, after):
    return before.keys() == after.keys() and all(
        math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-7)
        for key in before for a, b in zip(before[key], after[key]))


def _mark(item):
    """Attach a marker to each captured object; the fingerprint is the new baseline."""
    item["marks"] = []
    for index, entity in enumerate(item["entities"]):
        name = f"{item['id']}_{index}"
        try:
            entity.attributes.add(MARKER_GROUP, name, item["id"])
        except Exception:
            name = None  # E.g. referenced components: fall back to the in-memory reference.
        item["marks"].append(dict(name=name, fingerprint=_fingerprint(entity),
                                  info=_entity_info(entity)))


def _unmark(item):
    design = _design(item["document"])
    for mark in item.get("marks", []):
        if mark["name"] and design is not None:
            for attribute in _find_markers(design, mark["name"]):
                try:
                    attribute.deleteMe()
                except Exception:
                    pass
        mark["name"] = None


def _resolve(item):
    """Current objects and status of each captured selection."""
    design = _design(item["document"])
    rolled_back = design is not None and _rolled_back(design)
    resolved = []
    for index, (entity, mark) in enumerate(zip(item["entities"], item["marks"])):
        found = None
        if mark["name"] and design is not None and not rolled_back:
            markers = _find_markers(design, mark["name"])
            if markers:  # Undoing the capture can remove the marker; then use memory.
                parents = [_safe_attr(markers[0], "parent")]
                parents += list(_safe_attr(markers[0], "otherParents") or [])
                found = [p for p in parents if p is not None and _valid([p])]
        if found is None:
            found = [entity] if _valid([entity]) else []
        if rolled_back:
            status = "unverified"
        elif not found:
            status = "missing"
        elif len(found) > 1:
            status = "split"
        else:
            status = "ok" if _same_shape(mark["fingerprint"], _fingerprint(found[0])) else "changed"
            item["entities"][index] = found[0]  # Keep the fallback reference current.
        resolved.append(dict(status=status, entities=found, info=mark["info"]))
    return resolved


def _selections(item, resolved=None):
    if item["status"] == "done":  # Completed work is no longer tracked.
        return [{**mark["info"], "status": None} for mark in item["marks"]]
    return [{**r["info"], "status": r["status"], "valid": r["status"] != "missing",
             "parts": len(r["entities"])} for r in (resolved or _resolve(item))]


def _public(item, resolved=None):
    return {**{key: item[key] for key in ("id", "text", "status", "revision", "result")},
            "selections": _selections(item, resolved)}


def state():
    document = _document()
    design = _design(document) if document else None
    return {"document_id": document,
            "document_name": _safe_attr(_documents.get(document), "name"),
            "marker_count": len(_find_markers(design)) if design is not None else 0,
            "annotations": [_public(item) for item in STORE.items.values()
                            if item["document"] == document and not item["dismissed"]]}


def _require_document(expected=None):
    document = _document()
    if document is None:
        raise ValueError("Open a Fusion document first.")
    if expected is not None and expected != document:
        raise ValueError("Active document changed. Refresh and try again.")
    return document


def _captured(capture_id, document):
    if not _capture or _capture["id"] != capture_id or _capture["document"] != document:
        raise ValueError("Capture the selection again in this document.")
    if not _valid(_capture["entities"]):
        raise ValueError("The captured geometry changed. Capture the selection again.")
    return _capture["entities"]


def _capture_selection(document, pending=False):
    global _capture
    selections = get_app().userInterface.activeSelections
    entities = [selections.item(i).entity for i in range(selections.count)]
    if not entities or not _valid(entities):
        raise ValueError("Select one or more valid objects in Fusion first.")
    _capture = dict(id=uuid4().hex, document=document, entities=entities, pending=pending)
    return {"capture_id": _capture["id"], "selections": [_entity_info(e) for e in entities]}


def capture_for_palette():
    """Context-menu entry: capture now; the palette picks it up on its next read."""
    _capture_selection(_require_document(), pending=True)


def _ui_state():
    # Only the palette consumes a pending capture; MCP listing never does.
    payload = state()
    if _capture and _capture["pending"] and _capture["document"] == payload["document_id"]:
        _capture["pending"] = False
        payload["pending_capture"] = {"capture_id": _capture["id"],
                                      "selections": [_entity_info(e) for e in _capture["entities"]]}
    return payload


def ui_action(action, args):
    global _capture
    if action == "list":
        return _ui_state()
    if not args.get("document_id"):
        raise ValueError("Refresh the panel before continuing.")
    document = _require_document(args["document_id"])
    if action == "capture":
        return _capture_selection(document)
    if action == "create":
        _mark(STORE.create(document, args.get("text"), _captured(args.get("capture_id"), document)))
        _capture = None
    elif action == "edit":
        entities = _captured(args["capture_id"], document) if args.get("capture_id") else None
        previous = STORE.get(args.get("id"), document)
        was_done = previous["status"] == "done"
        old = dict(previous, marks=[dict(m) for m in previous["marks"]])
        item = STORE.edit(args.get("id"), document, args.get("revision"), args.get("text"), entities)
        if entities is not None or was_done:
            _unmark(old)
            _mark(item)
        _drop_references(args["id"])
        _capture = None
    elif action == "delete":
        item = STORE.get(args.get("id"), document)
        STORE.delete(args.get("id"), document, args.get("revision"))
        if args["id"] not in STORE.items:
            _drop_references(args["id"])
            _unmark(item)
    elif action == "select":
        item = STORE.get(args.get("id"), document)
        resolved = _resolve(item)
        if any(r["status"] == "missing" for r in resolved):
            raise ValueError("The original geometry is no longer available. Edit and recapture it.")
        selections = get_app().userInterface.activeSelections
        selections.clear()
        for entity in (e for r in resolved for e in r["entities"]):
            if not selections.add(entity):
                raise ValueError("Fusion cannot select this object in the current workspace.")
    elif action == "remove_markers":
        # Also removes markers left behind by crashes or saved versions.
        for attribute in _find_markers(_design(document)):
            try:
                attribute.deleteMe()
            except Exception:
                pass
        for item in STORE.items.values():
            if item["document"] == document:
                for mark in item["marks"]:
                    mark["name"] = None
    else:
        raise ValueError("Unknown annotation action.")
    return _ui_state()


def _warnings(resolved):
    messages = {
        "changed": "changed since it was captured; confirm it is still the intended target",
        "split": "was split; its references cover all resulting pieces",
        "unverified": "cannot be verified while the timeline is rolled back",
    }
    return [f"Selection {i + 1} ({r['info']['name'] or r['info']['objectType']}) {messages[r['status']]}."
            for i, r in enumerate(resolved) if r["status"] in messages]


def manage_annotations(args):
    """MCP boundary. Listing never claims, unlocks, or consumes annotations."""
    try:
        action = args.get("action", "list")
        if action == "list":
            payload = state()
        else:
            document = _require_document()
            item = STORE.get(args.get("id"), document)
            if action == "claim":
                resolved = _resolve(item)
                if any(r["status"] == "missing" for r in resolved):
                    raise ValueError("Selection is no longer in the design. Ask the user to edit and recapture it.")
                item = STORE.claim(item["id"], document, args.get("revision"))
                payload = {**_public(item, resolved), "claim_token": item["claim_token"],
                           "references": [], "warnings": _warnings(resolved)}
                for i, (r, selection) in enumerate(zip(resolved, payload["selections"])):
                    selection["references"] = []
                    for j, entity in enumerate(r["entities"]):
                        key = f"annotation_{item['id']}_{item['revision']}_{i}"
                        key += f"_{j}" if len(r["entities"]) > 1 else ""
                        value_builders.OBJECT_STORE[key] = entity
                        selection["references"].append(f"${key}")
                    payload["references"] += selection["references"]
            elif action in ("complete", "release"):
                if item["status"] == "in_progress":
                    _resolve(item)  # Refresh fallback references before markers go.
                item = STORE.finish(item["id"], document, args.get("claim_token"),
                                    args.get("result"), failed=action == "release")
                _drop_references(item["id"])
                if item["status"] == "done" or item["id"] not in STORE.items:
                    _unmark(item)
                payload = _public(item)
            else:
                raise ValueError("Unknown annotation action.")
        return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

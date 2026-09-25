"""Selection annotations shared by the Fusion palette and MCP tools.

All entry points run on Fusion's main thread, serializing claims and UI edits.
No annotations or object references are persisted to disk or the design.
"""

import json
from uuid import uuid4

from .annotation_store import AnnotationStore
from .dispatch import get_app
from . import value_builders
from .selection import _safe_attr, _get_parent_component

STORE = AnnotationStore()
_documents = {}
_capture = None


def clear():
    global _capture
    for item in STORE.items.values():
        _drop_references(item["id"])
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


def _public(item):
    return {**{key: item[key] for key in ("id", "text", "status", "revision", "result")},
            "selections": [_entity_info(entity) for entity in item["entities"]]}


def state():
    document = _document()
    return {"document_id": document,
            "document_name": _safe_attr(_documents.get(document), "name"),
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


def ui_action(action, args):
    global _capture
    if action == "list":
        return state()
    if not args.get("document_id"):
        raise ValueError("Refresh the panel before continuing.")
    document = _require_document(args["document_id"])
    if action == "capture":
        selections = get_app().userInterface.activeSelections
        entities = [selections.item(i).entity for i in range(selections.count)]
        if not entities or not _valid(entities):
            raise ValueError("Select one or more valid objects in Fusion first.")
        _capture = dict(id=uuid4().hex, document=document, entities=entities)
        return {"capture_id": _capture["id"], "selections": [_entity_info(e) for e in entities]}
    if action == "create":
        STORE.create(document, args.get("text"), _captured(args.get("capture_id"), document))
        _capture = None
    elif action == "edit":
        entities = _captured(args["capture_id"], document) if args.get("capture_id") else None
        STORE.edit(args.get("id"), document, args.get("revision"), args.get("text"), entities)
        _drop_references(args["id"])
        _capture = None
    elif action == "delete":
        STORE.delete(args.get("id"), document, args.get("revision"))
        if args["id"] not in STORE.items:
            _drop_references(args["id"])
    elif action == "select":
        item = STORE.get(args.get("id"), document)
        if not _valid(item["entities"]):
            raise ValueError("The original geometry is no longer available. Edit and recapture it.")
        selections = get_app().userInterface.activeSelections
        selections.clear()
        for entity in item["entities"]:
            if not selections.add(entity):
                raise ValueError("Fusion cannot select this object in the current workspace.")
    else:
        raise ValueError("Unknown annotation action.")
    return state()


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
                if not _valid(item["entities"]):
                    raise ValueError("Selection is no longer valid. Ask the user to edit and recapture it.")
                item = STORE.claim(item["id"], document, args.get("revision"))
                refs = []
                for i, entity in enumerate(item["entities"]):
                    key = f"annotation_{item['id']}_{item['revision']}_{i}"
                    value_builders.OBJECT_STORE[key] = entity
                    refs.append(f"${key}")
                payload = {**_public(item), "claim_token": item["claim_token"], "references": refs}
            elif action in ("complete", "release"):
                item = STORE.finish(item["id"], document, args.get("claim_token"),
                                    args.get("result"), failed=action == "release")
                _drop_references(item["id"])
                payload = _public(item)
            else:
                raise ValueError("Unknown annotation action.")
        return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

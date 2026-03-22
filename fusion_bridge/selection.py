"""Read the active selection from the Fusion 360 viewport."""

import json
import traceback

import adsk.core
import adsk.fusion

from . import value_builders
from .dispatch import get_app, log


def get_active_selection(arguments):
    """Return details of all currently selected objects in Fusion."""
    try:
        app = get_app()
        ui = app.userInterface
        selections = ui.activeSelections

        # Clear previous selection_* entries from store
        to_remove = [
            k for k in value_builders.OBJECT_STORE if k.startswith("selection_")
        ]
        for k in to_remove:
            del value_builders.OBJECT_STORE[k]

        result = {"count": selections.count, "selections": []}

        for i in range(selections.count):
            sel = selections.item(i)
            entity = sel.entity
            store_key = f"selection_{i}"

            # Store in object store for follow-up API calls
            value_builders.OBJECT_STORE[store_key] = entity

            item = {
                "index": i,
                "stored_as": store_key,
                "objectType": getattr(entity, "objectType", type(entity).__name__),
            }

            # Name (safe)
            name = _safe_attr(entity, "name")
            if name is not None:
                item["name"] = name

            # Entity token (safe)
            token = _safe_attr(entity, "entityToken")
            if token is not None:
                item["entityToken"] = token

            # Parent component path
            parent = _get_parent_component(entity)
            if parent is not None:
                item["parentComponent"] = parent

            # Type-aware extended properties
            props = _extract_extended_properties(entity)
            if props:
                item["properties"] = props

            result["selections"].append(item)

        context_msg = f"{len(value_builders.OBJECT_STORE)} objects in store"
        result["context"] = context_msg

        log(f"[MCP] get_active_selection: {result['count']} items")
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": False,
        }
    except Exception as exc:
        tb = traceback.format_exc()
        log(f"[MCP] get_active_selection failed: {exc}")
        return {
            "content": [{"type": "text", "text": f"Error: {exc}\n{tb}"}],
            "isError": True,
        }


def _safe_attr(obj, name):
    """Get attribute or return None on any error."""
    try:
        val = getattr(obj, name, None)
        return val
    except Exception:
        return None


def _get_parent_component(entity):
    """Try to determine the parent component path."""
    try:
        if hasattr(entity, "body") and entity.body:
            pc = entity.body.parentComponent
            if pc:
                return _safe_attr(pc, "name")
        if hasattr(entity, "parentComponent"):
            pc = entity.parentComponent
            if pc:
                return _safe_attr(pc, "name")
        if hasattr(entity, "component"):
            c = entity.component
            if c:
                return _safe_attr(c, "name")
    except Exception:
        pass
    return None


def _extract_extended_properties(entity):
    """Extract type-aware properties from the selected entity."""
    if entity is None:
        return {}

    props = {}

    # Bounding box (most types)
    bb = _safe_attr(entity, "boundingBox")
    if bb is not None:
        try:
            props["boundingBox"] = {
                "min": {"x": bb.minPoint.x, "y": bb.minPoint.y, "z": bb.minPoint.z},
                "max": {"x": bb.maxPoint.x, "y": bb.maxPoint.y, "z": bb.maxPoint.z},
            }
        except Exception:
            pass

    obj_type = getattr(entity, "objectType", "")

    # BRepBody
    if "BRepBody" in obj_type:
        vol = _safe_attr(entity, "volume")
        if vol is not None:
            props["volume"] = vol
        is_solid = _safe_attr(entity, "isSolid")
        if is_solid is not None:
            props["isSolid"] = is_solid
        is_visible = _safe_attr(entity, "isVisible")
        if is_visible is not None:
            props["isVisible"] = is_visible
        mat = _safe_attr(entity, "material")
        if mat is not None:
            mat_name = _safe_attr(mat, "name")
            if mat_name is not None:
                props["material"] = mat_name

    # BRepFace
    elif "BRepFace" in obj_type:
        area = _safe_attr(entity, "area")
        if area is not None:
            props["area"] = area
        centroid = _safe_attr(entity, "centroid")
        if centroid is not None:
            try:
                props["centroid"] = {"x": centroid.x, "y": centroid.y, "z": centroid.z}
            except Exception:
                pass

    # BRepEdge
    elif "BRepEdge" in obj_type:
        length = _safe_attr(entity, "length")
        if length is not None:
            props["length"] = length

    # Occurrence
    elif "Occurrence" in obj_type:
        is_visible = _safe_attr(entity, "isVisible")
        if is_visible is not None:
            props["isVisible"] = is_visible

    # Sketch
    elif "Sketch" in obj_type and "Curve" not in obj_type and "Point" not in obj_type:
        is_visible = _safe_attr(entity, "isVisible")
        if is_visible is not None:
            props["isVisible"] = is_visible
        curves = _safe_attr(entity, "sketchCurves")
        if curves is not None:
            count = _safe_attr(curves, "count")
            if count is not None:
                props["numberOfCurves"] = count

    return props

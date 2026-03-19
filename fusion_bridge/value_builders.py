"""Fusion API path resolution, object construction, argument coercion, and
result formatting.

The `FusionContext` class owns the object store and path-resolution logic.
Free functions `build_object` and `format_result` are independent utilities.
"""

import adsk.core
import adsk.fusion

from .dispatch import get_app


# ── Standalone utilities ──────────────────────────────────────────────────


def build_object(spec):
    """Construct an adsk SDK object from a ``{"type": ..., ...}`` descriptor."""
    type_name = spec.get("type")
    if not type_name:
        raise ValueError("Object spec is missing 'type'")

    fields = {k: v for k, v in spec.items() if k != "type"}

    # Fast-path well-known constructors
    if type_name == "ValueInput":
        if "expression" in fields:
            return adsk.core.ValueInput.createByString(str(fields["expression"]))
        if "value" in fields:
            return adsk.core.ValueInput.createByReal(float(fields["value"]))
        raise ValueError("ValueInput requires 'value' or 'expression'")

    if type_name == "ObjectCollection":
        return adsk.core.ObjectCollection.create()

    if type_name == "Matrix3D":
        return adsk.core.Matrix3D.create()

    # Search SDK modules for the type
    search_modules = [adsk.core, adsk.fusion]
    for optional in ("adsk.cam", "adsk.drawing"):
        try:
            search_modules.append(__import__(optional, fromlist=["*"]))
        except Exception:
            pass

    cls = None
    for mod in search_modules:
        cls = getattr(mod, type_name, None)
        if cls is not None:
            break
    if cls is None:
        raise ValueError(f"Unknown constructor type: {type_name}")

    try:
        if hasattr(cls, "create"):
            if type_name in ("Point3D", "Vector3D"):
                return cls.create(
                    fields.get("x", 0), fields.get("y", 0), fields.get("z", 0)
                )
            if type_name == "Point2D":
                return cls.create(fields.get("x", 0), fields.get("y", 0))
            return cls.create(**fields) if fields else cls.create()
        return cls(**fields)
    except TypeError as exc:
        raise ValueError(f"Failed to construct {type_name}: {exc}") from exc


def format_result(result, properties=None):
    """Return a *(type_name, summary_string)* tuple describing *result*."""
    type_name = type(result).__name__

    if result is None:
        return "NoneType", "None"
    if isinstance(result, (str, int, float, bool)):
        return type_name, str(result)

    if properties:
        selected = {}
        for field in properties:
            try:
                selected[field] = getattr(result, field)
            except Exception:
                selected[field] = "<unavailable>"
        return type_name, str(selected)

    try:
        if hasattr(result, "name"):
            return type_name, f"name='{getattr(result, 'name')}'"
        if hasattr(result, "count"):
            return type_name, f"count={getattr(result, 'count')}"
        if hasattr(result, "objectType"):
            return type_name, str(getattr(result, "objectType"))
    except Exception:
        pass

    return type_name, type_name


# ── FusionContext: object store + path resolution + coercion ─────────────


class FusionContext:
    """Maintains an object store and resolves dotted Fusion API paths."""

    _SHORTCUT_ROOTS = ("app", "ui", "design", "rootComponent")

    def __init__(self):
        self.objects = {}

    # -- store management --------------------------------------------------

    def store(self, name, obj):
        self.objects[name] = obj

    def clear(self):
        n = len(self.objects)
        self.objects.clear()
        return n

    @property
    def count(self):
        return len(self.objects)

    # -- path resolution ---------------------------------------------------

    def resolve_path(self, path):
        if not path:
            raise ValueError("api_path is required")

        if path.startswith("$"):
            return self._resolve_stored(path)

        root, remainder = self._split_root(path)
        return _walk(root, remainder)

    def _resolve_stored(self, path):
        name, _, tail = path[1:].partition(".")
        if name not in self.objects:
            raise ValueError(
                f"Stored object '{name}' not found. "
                f"Available: {sorted(self.objects.keys())}"
            )
        return _walk(self.objects[name], tail)

    def _split_root(self, path):
        """Determine the root object and the remaining attribute chain."""
        app = get_app()

        # Bare shortcut names
        _roots = {
            "app": lambda: app,
            "ui": lambda: app.userInterface,
            "design": lambda: app.activeProduct,
            "rootComponent": lambda: app.activeProduct.rootComponent,
        }
        if path in _roots:
            return _roots[path](), ""

        # Prefixed paths  (order matters — longest first)
        _prefixes = (
            ("adsk.drawing.", lambda: __import__("adsk.drawing", fromlist=["*"])),
            ("adsk.fusion.", lambda: adsk.fusion),
            ("adsk.core.", lambda: adsk.core),
            ("adsk.cam.", lambda: __import__("adsk.cam", fromlist=["*"])),
            ("rootComponent.", lambda: app.activeProduct.rootComponent),
            ("design.", lambda: app.activeProduct),
            ("ui.", lambda: app.userInterface),
            ("app.", lambda: app),
        )
        for prefix, root_fn in _prefixes:
            if path.startswith(prefix):
                return root_fn(), path[len(prefix) :]

        # Fallback — treat as attribute chain on the application object
        return app, path

    # -- argument coercion -------------------------------------------------

    def coerce_arg(self, value):
        """Recursively coerce raw JSON values into Fusion SDK objects where
        applicable."""
        if value is None or isinstance(value, (bool, int, float)):
            return value

        if isinstance(value, str):
            candidate = value.strip()
            looks_like_path = (
                candidate.startswith("$")
                or "." in candidate
                or candidate in self._SHORTCUT_ROOTS
            )
            if looks_like_path:
                try:
                    return self.resolve_path(candidate)
                except Exception:
                    return value
            return value

        if isinstance(value, dict):
            if "type" in value:
                return build_object(value)
            return {k: self.coerce_arg(v) for k, v in value.items()}

        if isinstance(value, list):
            return [self.coerce_arg(item) for item in value]

        return value


# ── Shared helpers ────────────────────────────────────────────────────────


def _walk(obj, dotted):
    """Traverse *obj* by the dotted attribute chain *dotted*."""
    current = obj
    if not dotted:
        return current
    for segment in dotted.split("."):
        if not segment:
            continue
        current = getattr(current, segment)
        if current is None:
            raise ValueError(f"Path resolved to None at '{segment}'")
    return current


# ── Module-level default context (backwards-compat shim) ─────────────────

_default_ctx = FusionContext()

# Expose thin wrappers so existing call-sites keep working.
OBJECT_STORE = _default_ctx.objects
resolve_path = _default_ctx.resolve_path
coerce_arg = _default_ctx.coerce_arg


def clear_object_store():
    return _default_ctx.clear()

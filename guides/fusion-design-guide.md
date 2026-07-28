# Fusion Design Guide

Use this guide when driving Autodesk Fusion through this MCP server.

Each capability is its own tool -- `call_autodesk_api`, `execute_python`,
`capture_viewport`, `get_active_selection`, `fetch_api_documentation`,
`fetch_online_documentation`, `fetch_design_guide` and the `*_script` tools.
The JSON blocks below show the arguments for the named tool; there is no
wrapping `operation` field.

## 1. Respect the Existing Design First

Before making any changes, inspect the open design and follow its established conventions.

- Check existing component structure, naming patterns, and user parameters.
- Match the naming style already in use (e.g. `Bracket_Left` vs `bracket-left`).
- Reuse existing user parameters instead of introducing new hardcoded values.
- If the design uses a particular unit system, stay consistent.
- Only fall back to the defaults in this guide when starting a brand-new design.

`execute_python`:

```json
{
  "description": "inspect existing design conventions",
  "code": "design = app.activeProduct\nprint(f'Units: {design.unitsManager.defaultLengthUnits}')\nprint(f'Components: {design.rootComponent.occurrences.count}')\nfor p in design.userParameters:\n    print(f'  Param: {p.name} = {p.expression}')"
}
```

## 2. Start With Intent

- Include a short `description` on tool calls so the Fusion log shows what is happening.
- Prefer small, reversible steps instead of one giant operation chain.
- When exploring the API, confirm object types and available members before writing a long script.

## 3. Pick the Right Access Pattern

- Use generic API calls for short, direct actions like creating a sketch or reading a property.
- Use `execute_python` when the task needs loops, branching, transactions, or repeated object lookup.
- Save reusable experiments with `save_script` so you can rerun a stable baseline quickly.

## 4. Always Work Inside a Component

Never model directly in the root component. Create a new component for each distinct part or sub-assembly.

- Each part gets its own component with a descriptive name.
- Components provide isolated timelines, independent origins, and clean assembly structure.
- Use `rootComponent.occurrences.addNewComponent()` to create a new component, then model inside it.
- For assemblies, create a top-level component per sub-assembly.

```python
transform = adsk.core.Matrix3D.create()  # identity = origin
occ = rootComponent.occurrences.addNewComponent(transform)
comp = occ.component
comp.name = "Motor_Mount"
# Now model inside comp, not rootComponent
sketch = comp.sketches.add(comp.xYConstructionPlane)
```

## 5. Use Parametric Design Patterns

Drive dimensions with user parameters, not hardcoded numbers.

- Create user parameters for key dimensions early (`design.userParameters.add()`).
- Reference parameters in `ValueInput.createByString()` so the model updates when parameters change.
- Add sketch constraints (coincident, concentric, tangent, equal, etc.) to keep geometry fully constrained.
- Prefer `dimensionConstraints` over absolute coordinates when positioning sketch geometry.

```python
params = design.userParameters
params.add("wall_thickness", adsk.core.ValueInput.createByString("3 mm"), "mm", "Wall thickness")
params.add("mount_width", adsk.core.ValueInput.createByString("40 mm"), "mm", "Mount plate width")

# Use parameters in features
vi = adsk.core.ValueInput.createByString("wall_thickness")
```

## 6. Respect Fusion's Coordinate Model

- X is left-to-right, Y is vertical, and Z is front-to-back.
- For floor-like sketches, start on the XZ plane and extrude in Y when you mean height.
- If dimensions feel rotated, inspect the plane choice before changing geometry math.

## 7. Name Things Early

- Name bodies immediately after creation.
- Name components, sketches, and construction helpers with descriptive stable names.
- Use stable names for occurrences when later steps depend on them.
- Do not rely on collection indexes for important downstream references.

## 8. Build Inputs Deliberately

- Use `ValueInput` with `expression` when units matter in the request payload.
- Use `ValueInput` with `value` only when you intentionally want Fusion internal units (cm).
- Construct points, vectors, matrices, and collections explicitly instead of encoding them as loose strings.

## 9. Favor Predictable Modeling Sequences

- Create reference geometry first, then sketches, then features, then appearance or material changes.
- For multi-step feature creation, compute key dimensions up front and print them during script execution.
- Prefer defining position during creation over moving bodies afterward when the API offers both paths.

## 10. Be Timeline Aware

Fusion's parametric timeline records every operation. Respect it.

- Features are ordered in the timeline; inserting or reordering affects downstream features.
- Use `design.timeline` to inspect the current state before adding features.
- When editing existing features, use `timelineObject.rollTo()` to roll back, then roll forward after.
- Avoid deleting timeline features that other features depend on -- check dependencies first.
- Group related operations so they appear as a logical block in the timeline.

```python
timeline = design.timeline
print(f"Timeline has {timeline.count} features")
# Roll back to a specific point
marker = timeline.markerPosition
timeline.markerPosition = 5  # roll to feature 5
# ... inspect or edit ...
timeline.markerPosition = marker  # restore
```

## 11. Position Components With Joints, Not Transforms

Use joints to assemble components -- never manually position with transform matrices.

- Joints maintain relationships when geometry changes.
- Use `JointOrigins` on faces, edges, or points to define connection points.
- Common joint types: `RigidJointType`, `RevoluteJointType`, `SliderJointType`.
- Prefer `asBuiltJoints` when components are already positioned correctly and you want to lock them.

```python
jointGeom1 = adsk.fusion.JointGeometry.createByPoint(comp1_origin_point)
jointGeom2 = adsk.fusion.JointGeometry.createByPoint(comp2_mount_point)
jointInput = rootComponent.joints.createInput(jointGeom1, jointGeom2)
jointInput.setAsRigidJointMotion()
joint = rootComponent.joints.add(jointInput)
joint.name = "Motor_to_Bracket"
```

## 12. Keep Undo Clean

Wrap complex edits in a Fusion transaction when the user should be able to undo the whole change at once.

```python
app.executeTextCommand('PTransaction.Start "Bracket Layout"')

try:
    sketch = rootComponent.sketches.add(rootComponent.xZConstructionPlane)
    # build geometry here
    app.executeTextCommand('PTransaction.Commit')
except Exception:
    app.executeTextCommand('PTransaction.Abort')
    raise
```

## 13. Use Documentation in Two Passes

1. Call `fetch_api_documentation` to discover likely classes, methods, or properties.
2. Call `fetch_online_documentation` when you need parameter tables, return types, or Autodesk samples.

Example discovery request, `fetch_api_documentation`:

```json
{
  "search_term": "ExtrudeFeature",
  "category": "class_name",
  "max_results": 5
}
```

Example reference request, `fetch_online_documentation`:

```json
{
  "class_name": "ExtrudeFeatures",
  "member_name": "createInput"
}
```

The reply adapts to the kind of page Autodesk serves. Method pages return
`syntax`, `return_type` and `parameters`; property pages return
`property_type` and `access`; class pages return `methods`, `properties` and
`accessed_from`, which is the fastest way to survey an unfamiliar class.
Every reply carries a `preview` boolean -- see section 17 before building on
anything it marks as true.

## 14. Use Python Sessions for Investigation

- Persistent sessions are useful for holding intermediate values between experiments.
- Put important final values into `_mcp_result` or `print()` them so the caller can inspect outcomes.
- Avoid UI prompts in scripts because modal dialogs block automation.

Example session, `execute_python`:

```json
{
  "description": "inspect active design units",
  "session_id": "inspection",
  "persistent": true,
  "code": "design = app.activeProduct\nprint(design.unitsManager.defaultLengthUnits)"
}
```

## 15. Verify Visible Results

- After geometry changes, inspect key properties or capture the viewport.
- Use `return_properties` on generic API calls when you need confirmation without writing a full script.
- If the result looks wrong, clear assumptions about stored objects before retrying.

Viewport example, `capture_viewport`:

```json
{
  "width": 1200,
  "height": 900
}
```

## 16. Reuse Context Carefully

- Store only objects you need for follow-up calls.
- Clear the stored object context when switching to a new modeling task.
- Prefer semantic names like `base_sketch`, `mount_body`, or `top_face_ref`.

## 17. Treat Preview APIs as Unstable

Roughly one in six `adsk.fusion` classes is marked "in preview state". Autodesk
renames and removes these between releases without a deprecation period, so
code that works today can break on the next update.

- Check before relying on a class: `fetch_online_documentation` returns a
  `preview` boolean for every class, method and property.
- Do not try to detect this at runtime. The preview warning is stripped from
  the compiled modules, so `cls.__doc__` looks identical for preview and
  stable classes -- it survives only in Autodesk's own documentation.
- Guard optional features with `hasattr` rather than assuming they exist.
- Prefer a stable equivalent when one exists.
- When only a preview API will do, isolate it behind one small function so a
  rename touches a single place.

```json
{
  "class_name": "FoldFeature"
}
```

```python
# Runtime guard, since the class may simply be absent on older versions.
if not hasattr(comp.features, "foldFeatures"):
    raise RuntimeError("Fold features are unavailable in this Fusion version")
```

This is not hypothetical. Between Fusion 2703 and 2704 the sheet metal corner
closure classes were renamed outright -- `CornerClosureFeatureDefinition`
became `CornerClosureDefinition`, `TwoBendCornerClosureInputDefinition` became
`TwoBendCornerClosureDefinition`, and so on. Twenty of the twenty-three classes
added in 2704 are preview.

## 18. Sheet Metal Follows a Fixed Order

Sheet metal modeling is order-sensitive: the rule governs thickness and bend
allowance, so it must be set before geometry is created, and the flat pattern
must come last.

1. Set the sheet metal rule on the component.
2. Create the base geometry, working inside a component as in section 4.
3. Fold along sketch lines.
4. Close corners and join edges.
5. Create the flat pattern.

Rules live on the design; the active one is a component property:

```python
rules = design.designSheetMetalRules          # rules stored in this document
library = design.librarySheetMetalRules       # shipped library
comp.activeSheetMetalRule = library.itemByName("Aluminum (mm)")
```

Folds are built from an input, with bend lines added one at a time. Note that
`bendAngle` is a `ValueInput`, and `linePosition` says where the sketch line
sits relative to the bend:

```python
folds = comp.features.foldFeatures
fold_input = folds.createInput(stationary_face)          # BRepFace that stays put
fold_input.bendLines.add(
    sketch_line,                                          # SketchLine
    adsk.core.ValueInput.createByString("90 deg"),
    adsk.fusion.FoldBendLinePositionTypes.CenterFoldBendLinePositionType,
    True,                                                 # allowBendRelief
)
fold_input.isUseCornerRelief = True
fold = folds.add(fold_input)
fold.name = "Front_Lip"
```

Corner closures and joins take two edges each:

```python
closures = comp.features.cornerClosureFeatures
closures.add(closures.createInput(dominant_edge, submissive_edge))

joins = comp.features.joinByBendFeatures
join_input = joins.createInput(edge_one, edge_two)
join_input.isUseSheetMetalRuleBendRadius = True
joins.add(join_input)
```

The flat pattern is generated from a face that stays flat, and is reachable
afterwards through the component:

```python
comp.createFlatPattern(stationary_face)
flat = comp.flatPattern
print(flat.flatBody.name, flat.bendLinesBody.name)
```

Everything in this section except `unfoldFeatures` and `refoldFeatures` is
preview API -- apply section 17 before depending on it. Signatures here were
read from Fusion 2704.1.36; verify with `fetch_online_documentation` if your
version differs.

## 19. Common Failure Patterns

- Modeling directly in rootComponent instead of creating a dedicated component.
- Hardcoded dimensions instead of user parameters.
- Positioning components with transforms instead of joints.
- Sketch created on the wrong plane.
- A string argument was treated as a literal when you meant an API path.
- A stored reference points at an object from an earlier design state.
- A feature succeeds, but unnamed result bodies make the next step ambiguous.
- Ignoring existing design conventions and introducing inconsistent naming or units.
- Depending on a preview class that was renamed in a newer Fusion release.
- Creating sheet metal geometry before setting the active sheet metal rule.
- Generating the flat pattern before folds and corner closures are complete.

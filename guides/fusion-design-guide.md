# Fusion Design Guide

Use this guide when driving Autodesk Fusion through the `autodesk_fusion` MCP tool.

## 1. Respect the Existing Design First

Before making any changes, inspect the open design and follow its established conventions.

- Check existing component structure, naming patterns, and user parameters.
- Match the naming style already in use (e.g. `Bracket_Left` vs `bracket-left`).
- Reuse existing user parameters instead of introducing new hardcoded values.
- If the design uses a particular unit system, stay consistent.
- Only fall back to the defaults in this guide when starting a brand-new design.

```json
{
  "operation": "execute_python",
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

Example discovery request:

```json
{
  "operation": "fetch_api_documentation",
  "search_term": "ExtrudeFeature",
  "category": "class_name",
  "max_results": 5
}
```

Example reference request:

```json
{
  "operation": "fetch_online_documentation",
  "class_name": "ExtrudeFeatures",
  "member_name": "createInput"
}
```

## 14. Use Python Sessions for Investigation

- Persistent sessions are useful for holding intermediate values between experiments.
- Put important final values into `_mcp_result` or `print()` them so the caller can inspect outcomes.
- Avoid UI prompts in scripts because modal dialogs block automation.

Example session:

```json
{
  "operation": "execute_python",
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

Viewport example:

```json
{
  "operation": "capture_viewport",
  "width": 1200,
  "height": 900
}
```

## 16. Reuse Context Carefully

- Store only objects you need for follow-up calls.
- Clear the stored object context when switching to a new modeling task.
- Prefer semantic names like `base_sketch`, `mount_body`, or `top_face_ref`.

## 17. Common Failure Patterns

- Modeling directly in rootComponent instead of creating a dedicated component.
- Hardcoded dimensions instead of user parameters.
- Positioning components with transforms instead of joints.
- Sketch created on the wrong plane.
- A string argument was treated as a literal when you meant an API path.
- A stored reference points at an object from an earlier design state.
- A feature succeeds, but unnamed result bodies make the next step ambiguous.
- Ignoring existing design conventions and introducing inconsistent naming or units.

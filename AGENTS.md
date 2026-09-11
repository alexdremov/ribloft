# AGENTS.md

Working knowledge for AI agents operating on the **RibLoft** repo.

## What this is

FreeCAD addon that lofts **corresponding wires** of two or more multi-wire
profiles (e.g. UAV rib sections) without the twisted/crossed geometry stock
Loft produces. On every recompute it: pairs wires between consecutive
profiles by optimal assignment (Hungarian, `freecad/RibLoft/assign.py`,
O(n³), brute-force cross-tested), matches each wire's start vertex/winding to
the neighbour's nearest corners (16 candidates per wire), then
`Part.makeLoft` per chain. Everything is derived, nothing baked.

Two flavours (both in `freecad/RibLoft/ribloft.py`):

| Flavour               | Object                      | Behaviour                                                                                              |
| --------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------ |
| `RibLoftFP`           | `Part::FeaturePython`       | standalone compound of rib solids                                                                      |
| `PartDesignRibLoftFP` | `PartDesign::FeaturePython` | additive: `BaseFeature.multiFuse(solids)` (+`Refine`), wired into the Body chain by `body.addObject()` |

`gui.py` — context-aware command `RibLoft_Create` (active Body → PartDesign
flavour, else Part flavour) + undo transaction wrapper.
`init_gui.py` — workbench + `Gui.addWorkbenchManipulator` injecting the
button into PartDesign's _"Part Design Modeling Features"_ toolbar.

Configurable per object (`WireMatch` Optimal/Index, `MatchCorners`,
`Solid`, `Ruled`, `Closed`, `MaxDegree`, PD-only `Refine`); defaults from
`App.ParamGet("User parameter:BaseApp/Preferences/Mod/RibLoft")`.
`onDocumentRestored` upgrades older documents **idempotently** — keep
`_init_properties` and `_attach_view_provider` idempotent when extending.

## Install (critical gotcha)

User's Mod dir must be a **symlink**:
`~/Library/Application Support/FreeCAD/v26-3/Mod/ribloft → ~/dev/ribloft`.
The user has twice (2026-09-11) replaced it with a stale directory copy —
old code runs silently while new files sit on disk, and tracebacks show
misleading line numbers from the new files. **Always `readlink` that path
before debugging behaviour.** Also clear `__pycache__` under the repo when
code changed under a running/stale interpreter.

## Dev environment

- FreeCAD 26.3.0 custom build: headless `/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd`,
  GUI `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD` (accepts a script path as argument).
- Source checkout for grounding: `~/DocumentsLocal/DevLocal/freecad`
  (see its own AGENTS.md; user runs a 26.3 weekly on macOS 27 beta).
- **Verify every Gui/App API name against that source before using it** —
  several "obvious" ones don't exist (see facts below).
- `freecadcmd` stdout is unreliable/buffered → write logs from inside scripts
  (`App.Console.PrintMessage` interleaves correctly).
- `App.Document` is not subscriptable — use `doc.getObject(name)`.
- zsh: bare `===` in a compound command parses as a command; the Bash tool's
  cwd resets between calls to the freecad checkout — use absolute paths /
  `git -C ~/dev/ribloft`.

## Testing (all three must pass before delivering)

1. Pure solver: `python3 -m unittest discover -s tests` (no FreeCAD needed).
2. Headless features: `freecadcmd ~/dev/ribloft/tests/smoke_feature.py`
   (deliberately not named `test_*` so unittest skips it). Includes a
   backward-compat section against the real `pod-fixed.FCStd`
   (`~/DocumentsLocal/DevLocal/uav/cad/`) — 17 solids expected.
3. Real-GUI end-to-end (the only way to test the command/VP layer):
   `/Applications/FreeCAD.app/Contents/MacOS/FreeCAD /tmp/ribloft_guitest.py`
   — pattern: `Gui.activateWorkbench("PartDesignWorkbench")`, open a **/tmp
   copy** of the doc, `view.setActiveObject("pdbody", body)`, re-select
   sources before **each** `Gui.runCommand("RibLoft_Create")` (the command
   clears the selection), assert on created objects/Tip/solids, log to a
   file, close docs, `os._exit(code)` (never hard-kill with docs open —
   recovery prompts). A reference harness existed at `/tmp/ribloft_guitest.py`.

Geometry-assert gotchas: volume is shear-invariant (Cavalieri) — probe
parametric "follow" with BoundBox, not volume; `Part.Compound` has no
`CenterOfMass`; OCC's `ThruSections` auto-fixes simple rotated sections, so
twist tests need geometric asserts (side-face count/planarity), and the
MatchCorners=Off path only asserts "recomputes without error".

## Verified API facts (source-grounded — do not "simplify" these back)

- **`Gui.Document` has NO `ActiveBody` attribute** (AttributeError in the
  field). The active body is the 3D view's active object:
  `Gui.ActiveDocument.ActiveView.getActiveObject("pdbody")` — canonical, see
  `src/Mod/PartDesign/InvoluteGearFeature.py:47`. Set it with
  `view.setActiveObject("pdbody", body)` (equivalent to double-click).
  `gui.py` falls back: document with exactly one Body → auto-activate it
  (mirrors C++ `PartDesignGui::getBody`); else the one Body that contains the
  entire selection (`obj.getParentGeoFeatureGroup()`).
- **ViewProvider:** `PartDesignGui::ViewProviderPython` is
  `Gui::ViewProviderFeaturePythonT<PartDesignGui::ViewProvider>`;
  `ViewProviderFeaturePythonImp` dispatches **no-argument**
  `claimChildren(self)` and `getIcon(self)` to the Python proxy stored on
  `obj.ViewObject.Proxy`. That's how source sketches show as tree children.
  Attach `ViewProviderRibLoft` in both factories and in
  `onDocumentRestored`, always `FreeCAD.GuiUp`-guarded and idempotent.
- **Tree eye click** (`src/Gui/Tree.cpp` mousePressEvent): tries
  `parent.isElementVisible(name)` first — a Body returns −1 (nobody
  implements it) — then sets the object's `Visibility` property;
  `PartDesignGui::ViewProvider::onChanged` enforces one-visible-feature per
  body. Works for our plain scripted VP. If the _whole Body_ is hidden, a
  visible feature still shows nothing in 3D — that's user confusion, not a
  bug.
- `body.addObject()` auto-wires `BaseFeature`/`Tip` and **rejects non-
  PartDesign objects** ("Body: object is not allowed") → the Part flavour
  joins a container via direct `body.Group = body.Group + [obj]` (stays in
  link scope, Tip untouched). Multi-solid bodies are fine
  (`AllowCompound` default true).
- Container membership must exist **before the first recompute**, else one
  out-of-scope warning fires; links must stay within one Body/App::Part
  (`GeoFeatureGroupExtension::isLinkValid`).
- Workbench injection: `Gui.addWorkbenchManipulator` with
  `modifyToolBars()` returning
  `[{"append": "RibLoft_Create", "toolBar": "Part Design Modeling Features"}]`
  (silently skipped in workbenches lacking that toolbar; fallback is
  Tools → Customize).

## Document quirks (user's UAV files — not RibLoft bugs)

- `pod-fixed.FCStd` is the working test document: additive RibLoft inside
  Body005 'Ribs' (Tip=RibLoft over Pad007, 17 solids, vol 311181.5).
- First open per process prints `Cyclic sub-object reference to
wing#Assembly` / "The graph must be a DAG." — pre-existing cyclic
  SubShapeBinder in the user's files (fixed upstream, warning only).
- wing.FCStd's Fixed `Joint` sits in an orphaned `Joints` group (empty
  InList, outside `Assembly`) → stock Assembly workbench spams
  `JointObject.py:1221 getOverlayIcons` AttributeError ('NoneType' …
  `isPartConnected`). Cosmetic; 2-line upstream guard exists as an option —
  file upstream **only on explicit instruction**.
- NEVER write `pod.FCStd` while the GUI has it open (`pgrep -x freecad`);
  deliver `-fixed` copies.

## Git conventions

- **The user manages this repo**: they create commits (sometimes titled
  "fix") and may commit AI working-tree changes themselves. Check
  `git status`/`git log` before assuming anything needs committing; never
  rewrite their history.
- Commits made by AI carry the trailer
  `Assisted-by: GLM-5.3-Flash (Z.ai)` (user reviews and vouches); no pushes
  anywhere without explicit instruction (there is no remote yet).
- Version lives in TWO places, keep in sync: `freecad/RibLoft/__init__.py`
  `__version__` and `package.xml` `<version>` (both occurrences).

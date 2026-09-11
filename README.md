# RibLoft

Parametric lofts through **corresponding wires** of multi-wire profiles —
built for ribs, frames, stringers and bulkheads lofted between section
sketches that each hold several closed profiles (one per rib).

FreeCAD's stock Loft matches sections by each wire's *start vertex and
direction*. If your sections are rotated, re-ordered or re-drawn, corners
connect to the wrong corners and every loft twists into a bow-tie. RibLoft
removes that whole class of failure:

- **Optimal wire pairing** — wires of consecutive profiles are matched by
  minimum total centroid distance using the Hungarian algorithm
  (Kuhn–Munkres, O(n³)). Wire order inside the sketches does not matter.
- **Automatic corner matching** — every wire's start vertex and winding are
  re-oriented to its neighbour's nearest corners before lofting, so
  corresponding corners connect and rotated sections cannot twist the loft.
- **Fully parametric** — all pairing and matching is redone on every
  recompute: edit your sketches and the ribs follow. No detached geometry.
- **N stations** — two or more profiles loft into continuous wire chains
  (e.g. leading edge → trailing edge → motor mount).

## Install

**Addon Manager** (once published): *Tools → Addon Manager → RibLoft*.

Manual:

```sh
git clone https://github.com/alexdremov/ribloft.git
ln -s "$(pwd)/ribloft" ~/Library/"Application Support"/FreeCAD/vX-Y/Mod/RibLoft   # macOS
# ~/.local/share/FreeCAD/Mod/RibLoft      (Linux)
# %APPDATA%\FreeCAD\Mod\RibLoft           (Windows)
```

Restart FreeCAD; a *RibLoft* workbench with a single toolbar button appears.

## Usage

1. Sketch your sections: each profile object (sketch or any Part feature)
   holds one **closed wire per rib**, all in one plane (or not — only the
   pairwise correspondence matters).
2. Select the profile objects **in flow order** (first = start section).
3. Press the **RibLoft** button (or run the API below). The feature is
   created in the same Body / App::Part as the first selected profile, so
   links stay in scope.

Python:

```python
from freecad.RibLoft import ribloft
ribloft.makeRibLoft(App.ActiveDocument, ["SketchSectionA", "SketchSectionB"],
                    label="RibsAB", container=my_body)
```

## Properties

| Property       | Default | Meaning |
|----------------|---------|---------|
| `Sources`      | —       | Profile objects, in flow order. |
| `WireMatch`    | `Optimal` | `Optimal`: pair wires by minimum total centroid distance (Hungarian). `Index`: pair by wire order as-is. |
| `MatchCorners` | `True`  | Re-orient each wire (start vertex + winding) to its neighbour's nearest corners before lofting. Off = plain OCC matching. |
| `Solid`        | `True`  | Solids instead of shells. |
| `Ruled`        | `True`  | Straight ruling between sections; off = smooth B-spline through the sections. |
| `Closed`       | `False` | Close the loft by returning to the first profile. |
| `MaxDegree`    | `5`     | Maximum B-spline degree in smooth mode. |

Defaults for *new* features can be preset in
`Tools → Edit Parameters → BaseApp/Preferences/Mod/RibLoft`
(`WireMatch`, `MatchCorners`, `Solid`, `Ruled`, `Closed`, `MaxDegree`).

## Notes & limitations

- Each profile must contain the **same number of wires** (one wire per rib
  in every section).
- Wires should be planar closed loops; straight-line wires are the tested
  path, curved edges work via the edge-rotation matching but are less
  battle-tested.
- The result is a `Part::FeaturePython` holding a compound of solids. It
  can live inside a Body's `Group` (directly set — the feature is not a
  PartDesign feature and never becomes the Tip); reference it from other
  bodies via a ShapeBinder as usual.
- Wire pairing is geometric: two rib layouts that are *equally* close to
  their neighbour sections are resolved by minimal total distance — which
  is the intended "ribs continue to their nearest continuation" behaviour.
- Documents embedding RibLoft features require this addon installed to
  recompute (otherwise the last computed shape is still shown).

## Development

```sh
python3 -m unittest discover -s tests -v          # Hungarian solver vs brute force
freecadcmd tests/smoke_feature.py                 # FreeCAD feature smoke test (needs freecadcmd, not plain python)
```

## License

[MIT](LICENSE)

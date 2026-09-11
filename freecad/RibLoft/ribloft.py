"""RibLoft — parametric loft through corresponding wires of multi-wire profiles.

One RibLoft object takes two or more profile objects (e.g. sketches holding one
closed wire per rib) and lofts each wire chain into a solid. Between
consecutive profiles, wires are paired by minimum total centroid distance
(Hungarian algorithm), and every wire's start vertex / winding is matched to
its neighbour's nearest corners before lofting. Both steps are configurable
per object; everything is redone on each recompute, so editing the sketches
updates the loft.

Usage (Python console / macro):

    from freecad.RibLoft import ribloft
    ribloft.makeRibLoft(FreeCAD.ActiveDocument, ["Sketch", "Sketch001"],
                        label="MyRibs", container=some_body)
"""

import math

import FreeCAD
import Part

from freecad.RibLoft import assign

__version__ = "0.1.0"

WIRE_MATCH_MODES = ["Optimal", "Index"]

_PARAMS = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/RibLoft")


def _init_properties(obj):
    """Declare all RibLoft properties.

    Idempotent: safe to call again for objects restored from documents saved
    by older RibLoft versions, which are upgraded in place.
    """
    if not hasattr(obj, "Sources"):
        obj.addProperty(
            "App::PropertyLinkList", "Sources", "RibLoft",
            "Profile objects to loft (one closed wire per rib), in flow order")
    if not hasattr(obj, "WireMatch"):
        obj.addProperty(
            "App::PropertyEnumeration", "WireMatch", "RibLoft",
            "How wires of consecutive profiles are paired: Optimal = minimum "
            "total centroid distance (Hungarian algorithm); Index = wire "
            "order as-is")
        obj.WireMatch = WIRE_MATCH_MODES
        obj.WireMatch = _PARAMS.GetString("WireMatch", "Optimal")
    if not hasattr(obj, "MatchCorners"):
        obj.addProperty(
            "App::PropertyBool", "MatchCorners", "RibLoft",
            "Rotate each wire's start vertex and winding to its neighbour's "
            "nearest corners before lofting; prevents twisted lofts")
        obj.MatchCorners = _PARAMS.GetBool("MatchCorners", True)
    if not hasattr(obj, "Solid"):
        obj.addProperty(
            "App::PropertyBool", "Solid", "RibLoft",
            "Build solids instead of shells")
        obj.Solid = _PARAMS.GetBool("Solid", True)
    if not hasattr(obj, "Ruled"):
        obj.addProperty(
            "App::PropertyBool", "Ruled", "RibLoft",
            "Straight ruling between sections instead of smooth B-splines")
        obj.Ruled = _PARAMS.GetBool("Ruled", True)
    if not hasattr(obj, "Closed"):
        obj.addProperty(
            "App::PropertyBool", "Closed", "RibLoft",
            "Close the loft by returning to the first profile")
        obj.Closed = _PARAMS.GetBool("Closed", False)
    if not hasattr(obj, "MaxDegree"):
        obj.addProperty(
            "App::PropertyInteger", "MaxDegree", "RibLoft",
            "Maximum B-spline degree (smooth mode)")
        obj.MaxDegree = _PARAMS.GetInt("MaxDegree", 5)


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _centroids(wires):
    return [(w.CenterOfMass.x, w.CenterOfMass.y, w.CenterOfMass.z)
            for w in wires]


def _pair(prev_pts, cur_pts, mode):
    """Map cur wire index -> prev wire index, honouring the match mode."""
    n = len(prev_pts)
    if len(cur_pts) != n:
        raise ValueError(
            "RibLoft: profiles have different wire counts (%d vs %d)"
            % (n, len(cur_pts)))
    if mode == "Optimal":
        cost = [[_dist2(p, c) for c in cur_pts] for p in prev_pts]
        return assign.solve(cost)  # col_of_row[i] = cur wire for prev wire i
    return list(range(n))


def _loop(wire):
    """Cyclically ordered vertex coordinates of a closed wire."""
    pts = [(v.Point.x, v.Point.y, v.Point.z) for v in wire.OrderedVertexes]
    if len(pts) > 1 and _dist2(pts[0], pts[-1]) < 1e-12:
        pts = pts[:-1]
    return pts


def _orient(loop, target):
    """(rotation, flip) of `loop` whose vertex k best matches target[k]."""
    n = len(loop)
    best, bestc = (0, False), float("inf")
    for rot in range(n):
        for flip in (False, True):
            cand = loop[rot:] + loop[:rot]
            if flip:
                cand = [cand[0]] + cand[1:][::-1]
            c = sum(_dist2(cand[k], target[k]) for k in range(n))
            if c < bestc:
                bestc, best = c, (rot, flip)
    return best


def _reoriented(wire, rot, flip):
    """Same wire, started `rot` edges later; traversed backwards if flip."""
    edges = list(wire.OrderedEdges)
    edges = edges[rot:] + edges[:rot]
    if flip:
        edges = edges[:1] + edges[1:][::-1]
        out = []
        for e in edges:
            e = e.copy()
            e.Orientation = "Reversed" if e.Orientation == "Forward" else "Forward"
            out.append(e)
        edges = out
    return Part.Wire(edges)


def _chain_loft(wires, match_corners, solid, ruled, closed, max_degree):
    """Loft a chain of wires; align start vertices/windings to the previous
    section if `match_corners`, so corresponding corners connect."""
    if match_corners:
        aligned = [wires[0]]
        for w in wires[1:]:
            rot, flip = _orient(_loop(w), _loop(aligned[-1]))
            aligned.append(_reoriented(w, rot, flip))
        wires = aligned
    return Part.makeLoft(wires, solid, ruled, closed, max_degree)


class RibLoftFP:
    """Proxy for the RibLoft scripted feature."""

    def __init__(self, obj):
        _init_properties(obj)
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        # Documents saved by older RibLoft versions lack newer properties.
        _init_properties(obj)

    def execute(self, obj):
        if not obj.Sources:
            obj.Shape = Part.Shape()
            return
        shapes = []
        for s in obj.Sources:
            sh = s.Shape.copy()
            if hasattr(s, "getGlobalPlacement"):
                sh.Placement = s.getGlobalPlacement()
            shapes.append(sh)
        # Work in this feature's own coordinate system, so a non-identity
        # placement of a parent (Body, App::Part) does not double-transform
        # the result.
        inv = obj.getGlobalPlacement().inverse()
        for sh in shapes:
            sh.Placement = inv.multiply(sh.Placement)

        wire_sets = [list(sh.Wires) for sh in shapes]
        if not wire_sets[0]:
            raise ValueError("RibLoft: first source has no wires")
        chains = [[w] for w in wire_sets[0]]
        for ws in wire_sets[1:]:
            perm = _pair(_centroids([c[-1] for c in chains]),
                         _centroids(ws), obj.WireMatch)
            for i, j in enumerate(perm):
                chains[i].append(ws[j])

        solids = []
        for k, chain in enumerate(chains):
            try:
                loft = _chain_loft(chain, obj.MatchCorners, obj.Solid,
                                   obj.Ruled, obj.Closed, obj.MaxDegree)
            except Exception as e:
                raise ValueError(
                    "RibLoft: loft of wire chain %d failed: %s" % (k + 1, e))
            if loft.isNull() or not loft.isValid():
                raise ValueError(
                    "RibLoft: wire chain %d produced an invalid shape"
                    % (k + 1))
            solids.append(loft)
        obj.Shape = Part.Compound(solids)

    # persistence ---------------------------------------------------------
    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def makeRibLoft(doc, sources, name="RibLoft", label=None, container=None):
    """Create a RibLoft in `doc`; `sources` = objects or names, in flow order.

    `container` (optional): a geo feature group (Body, App::Part) to put the
    feature into before the first recompute — should hold the sources too,
    or FreeCAD prints an out-of-scope link warning.
    """
    if isinstance(sources, str) or not hasattr(sources, "__iter__"):
        sources = [sources]
    objs = [doc.getObject(s) if isinstance(s, str) else s for s in sources]
    obj = doc.addObject("Part::FeaturePython", name)
    RibLoftFP(obj)
    if container is not None:
        container.Group = list(container.Group) + [obj]
    obj.Sources = objs
    if label:
        obj.Label = label
    doc.recompute()
    return obj

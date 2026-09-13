"""RibLoft feature smoke test. Run headless:

    freecadcmd tests/smoke_feature.py

Covers: optimal pairing on shuffled sections, corner matching on/off,
wire-match modes, parametric follow, proxy restore, and (if present)
backward compatibility with a real document embedding an older RibLoft.
"""

import math
import os

import FreeCAD as App
import Part

from freecad.RibLoft import ribloft

OUT = "/tmp/ribloft_smoke.FCStd"
LOG = "/tmp/ribloft_smoke.log"
SIZE = 10.0
SPAN = 60.0


def P(*a):
    with open(LOG, "a") as f:
        print(*a, file=f)
        f.flush()


def square_wire(x, cy, cz):
    """Closed square wire (SIZE x SIZE) in the plane X=x, centred (cy, cz),
    vertices starting at the (-Y, -Z) corner."""
    o = App.Vector(x, cy - SIZE / 2, cz - SIZE / 2)
    u = App.Vector(0, SIZE, 0)
    v = App.Vector(0, 0, SIZE)
    pts = [o, o + u, o + u + v, o + v]
    return Part.Wire([Part.LineSegment(pts[k], pts[(k + 1) % 4]).toShape()
                      for k in range(4)])


def feature(doc, name, wires):
    f = doc.addObject("Part::Feature", name)
    f.Shape = Part.Compound(wires) if len(wires) > 1 else wires[0]
    return f


def side_face_planarity(solid):
    """(#planar side faces, #side faces). Side faces span the loft in X;
    the cap faces sit in the two section planes and have zero X extent."""
    side = [f for f in solid.Faces if f.BoundBox.XLength > 1.0]
    planar = sum(1 for f in side if isinstance(f.Surface, Part.Plane))
    return planar, len(side)


def run():
    if os.path.exists(LOG):
        os.remove(LOG)
    P("=== RibLoft smoke test ===")

    # ---- 1. corner matching on a single rib, rotated target section -------
    doc = App.newDocument("corner")
    wa = square_wire(0, 0, 0)
    wb = square_wire(SPAN, 0, 0)
    wb.rotate(App.Vector(SPAN, 0, 0), App.Vector(1, 0, 0), 90.0)  # 90 deg in-plane
    fa = feature(doc, "ProfA", [wa])
    fb = feature(doc, "ProfB", [wb])

    rib = ribloft.makeRibLoft(doc, [fa, fb], label="CornerRib")
    solid = rib.Shape.Solids[0]
    planar, nside = side_face_planarity(solid)
    P("matched: vol=%.1f area=%.1f side faces=%d planar=%d"
      % (solid.Volume, solid.Area, nside, planar))
    assert nside == 4 and planar == 4, "corner matching failed: twisted faces"
    assert abs(solid.Volume - SIZE * SIZE * SPAN) < 1e-4, solid.Volume

    # Corner matching OFF hands the raw wires to OCC's ThruSections, whose
    # internal compatibility search may or may not fix the corners depending
    # on the geometry (it rescues this simple case, but failed on the real
    # pod sections that motivated RibLoft). No twist guarantee is asserted
    # here; the contract is that MatchCorners=True is always exact.
    rib.MatchCorners = False
    doc.recompute()
    assert rib.Shape.isValid() and len(rib.Shape.Solids) == 1
    P("corners off: recomputed OK (OCC fallback path)")
    rib.MatchCorners = True
    doc.recompute()
    assert abs(rib.Shape.Solids[0].Volume - SIZE * SIZE * SPAN) < 1e-4
    App.closeDocument(doc.Name)

    # ---- 2. optimal pairing on a 6-wire ring with reversed target order ---
    doc = App.newDocument("pairing")
    centers = [(30.0 * math.cos(2 * math.pi * k / 6),
                30.0 * math.sin(2 * math.pi * k / 6)) for k in range(6)]
    wa = [square_wire(0, cy, cz) for cy, cz in centers]
    wb = [square_wire(SPAN, cy, cz) for cy, cz in centers]
    wb = wb[::-1]  # reversed: index pairing must fail, optimal must not
    fa = feature(doc, "ProfA", wa)
    fb = feature(doc, "ProfB", wb)

    rib = ribloft.makeRibLoft(doc, [fa, fb], label="RingRibs")
    solids = rib.Shape.Solids
    P("optimal: solids=%d valid=%s vol=%.1f"
      % (len(solids), rib.Shape.isValid(), rib.Shape.Volume))
    assert len(solids) == 6 and rib.Shape.isValid()
    # ribs must be straight prisms through the ring: no overlaps, exact span
    for s in solids:
        bb = s.BoundBox
        assert abs((bb.XMax - bb.XMin) - SPAN) < 1e-6
        assert abs(s.Volume - SIZE * SIZE * SPAN) < 1e-4, s.Volume
    overlap = sum(a.common(b).Volume
                  for i, a in enumerate(solids) for b in solids[i + 1:])
    P("optimal: pairwise overlap volume=%.6f" % overlap)
    assert overlap < 1e-6, overlap

    rib.WireMatch = "Index"
    doc.recompute()
    solids_idx = rib.Shape.Solids
    overlap_idx = sum(a.common(b).Volume
                      for i, a in enumerate(solids_idx)
                      for b in solids_idx[i + 1:])
    P("index: overlap volume=%.1f" % overlap_idx)
    assert overlap_idx > 1.0, "index pairing unexpectedly fine"
    rib.WireMatch = "Optimal"
    doc.recompute()

    # ---- 3. parametric follow --------------------------------------------
    x0 = rib.Shape.BoundBox.XMax
    fb.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation())
    doc.recompute()
    x1 = rib.Shape.BoundBox.XMax
    P("follow: XMax %.2f -> %.2f" % (x0, x1))
    assert abs((x1 - x0) - 5.0) < 1e-6
    fb.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
    doc.recompute()

    doc.saveAs(OUT)
    App.closeDocument(doc.Name)

    # ---- 4. proxy restore --------------------------------------------------
    doc = App.openDocument(OUT)
    rib = doc.getObject("RibLoft")
    assert rib is not None
    assert type(rib.Proxy).__name__ == "RibLoftFP"
    assert rib.WireMatch == "Optimal" and rib.MatchCorners is True
    rib.touch()
    doc.recompute()
    assert len(rib.Shape.Solids) == 6 and rib.Shape.isValid()
    P("restore+recompute: OK")
    App.closeDocument(doc.Name)

    # ---- 5. PartDesign additive mode ---------------------------------------
    doc = App.newDocument("pd")
    body = doc.addObject("PartDesign::Body", "Body")
    sk = doc.addObject("Sketcher::SketchObject", "BaseSketch")
    pts = [App.Vector(0, 0, 0), App.Vector(20, 0, 0),
           App.Vector(20, 10, 0), App.Vector(0, 10, 0)]
    for k in range(4):
        sk.addGeometry(Part.LineSegment(pts[k], pts[(k + 1) % 4]), False)
    body.addObject(sk)
    pad = doc.addObject("PartDesign::Pad", "Pad")
    pad.Profile = sk
    pad.Length = 10.0
    body.addObject(pad)
    doc.recompute()
    assert pad.Shape.isValid() and body.Tip == pad
    pad_vol = pad.Shape.Volume

    ring = [(30.0 * math.cos(2 * math.pi * k / 3),
             30.0 * math.sin(2 * math.pi * k / 3)) for k in range(3)]
    wa = [square_wire(100, cy, cz) for cy, cz in ring]
    wb = [square_wire(160, cy, cz) for cy, cz in ring][::-1]
    fa = feature(doc, "ProfA2", wa)
    fb = feature(doc, "ProfB2", wb)
    body.Group = list(body.Group) + [fa, fb]  # keep links in scope

    rib = ribloft.makePartDesignRibLoft(doc, [fa, fb], body, label="PDRibs")
    P("pd: type=%s tip=%s base=%s" % (
        rib.TypeId, body.Tip.Name,
        rib.BaseFeature.Name if rib.BaseFeature else None))
    assert rib.TypeId == "PartDesign::FeaturePython"
    assert body.Tip == rib
    assert rib.BaseFeature == pad
    assert "Error" not in rib.State and "Invalid" not in rib.State
    expected = pad_vol + 3 * SIZE * SIZE * SPAN  # disjoint: exact sum
    assert abs(body.Shape.Volume - expected) < 1e-3, (
        body.Shape.Volume, expected)
    assert len(body.Shape.Solids) == 4  # multi-solid body (AllowCompound)

    # parametric follow through the PD chain
    fb.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation())
    doc.recompute()
    bb = body.Shape.BoundBox
    P("pd follow: XMax=%.1f (expect 165.0)" % bb.XMax)
    assert abs(bb.XMax - 165.0) < 1e-6
    fb.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
    doc.recompute()

    doc.saveAs("/tmp/ribloft_smoke_pd.FCStd")
    App.closeDocument(doc.Name)
    doc = App.openDocument("/tmp/ribloft_smoke_pd.FCStd")
    rib = doc.getObject("RibLoft")
    assert type(rib.Proxy).__name__ == "PartDesignRibLoftFP"
    assert doc.getObject("Body").Tip == rib
    rib.touch()
    doc.recompute()
    assert "Error" not in rib.State
    P("pd restore+recompute: OK (vol=%.1f)" % doc.getObject("Body").Shape.Volume)
    App.closeDocument(doc.Name)

    # ---- 6. backward compat with a real document saved by an older version
    candidates = [
        "/Users/alexdremov/DocumentsLocal/DevLocal/uav/cad/pod-fixed.FCStd",
        "/Users/alexdremov/DocumentsLocal/DevLocal/uav/cad/pod.FCStd",
    ]
    real = next((p for p in candidates if os.path.exists(p)), None)
    if real:
        doc = App.openDocument(real)
        ribs = [o for o in doc.Objects if o.Name.startswith("RibLoft")]
        assert ribs, "no RibLoft objects in %s" % real
        for old in ribs:
            assert hasattr(old, "WireMatch"), \
                "onDocumentRestored did not upgrade properties"
            assert old.WireMatch == "Optimal"
            assert hasattr(old, "MatchCorners") and old.MatchCorners is True
            old.touch()
        doc.recompute()
        for old in ribs:
            assert old.Shape.isValid() and len(old.Shape.Solids) >= 1
            P("%s compat: OK (%s, %d solids, vol %.1f)"
              % (os.path.basename(real), old.Name,
                 len(old.Shape.Solids), old.Shape.Volume))
        App.closeDocument(doc.Name)
    else:
        P("no real UAV document found; compat check skipped")

    P("=== ALL SMOKE TESTS PASSED ===")


run()

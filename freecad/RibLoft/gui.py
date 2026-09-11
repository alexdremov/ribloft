# SPDX-License-Identifier: MIT
# GUI wiring for RibLoft. Only imported from init_gui.py (i.e. with a GUI
# session); the document-restore path never touches this module.

import FreeCAD
import FreeCADGui

from freecad.RibLoft import ICONPATH
from freecad.RibLoft import ribloft


class RibLoftCommand:
    """Create a RibLoft from the selected profile objects.

    Context-sensitive: with an active PartDesign Body the ribs are fused into
    that body's feature chain (additive, like an AdditiveLoft); without one a
    standalone Part feature holding the rib compound is created in the
    profiles' container.
    """

    def GetResources(self):
        return {
            "Pixmap": ICONPATH + "/ribloft.svg",
            "MenuText": "RibLoft",
            "ToolTip": "Loft corresponding wires of two or more multi-wire "
                       "profiles. Wires are paired between profiles and "
                       "corner-matched automatically, so rotated or "
                       "re-ordered sections do not produce twisted lofts. "
                       "Select the profiles in flow order. With an active "
                       "Body the ribs are fused into it additively.",
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        sel = FreeCADGui.Selection.getSelection()
        if len(sel) < 2:
            FreeCAD.Console.PrintError(
                "RibLoft: select at least two profile objects "
                "(sketches with one closed wire per rib), in flow order\n")
            return
        doc = FreeCAD.ActiveDocument

        body = self._active_body(doc, sel)
        doc.openTransaction("RibLoft")
        try:
            if body is not None:
                self._activate_design(doc, sel, body)
            else:
                self._activate_part(doc, sel)
        except Exception:
            doc.abortTransaction()
            raise
        doc.commitTransaction()

    @staticmethod
    def _active_body(doc, sel):
        """The Body the ribs should join, mirroring PartDesignGui::getBody().

        Gui.Document has no ActiveBody attribute; the active body lives on the
        3D view as the 'pdbody' active object (set by double-clicking a body).
        """
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
        except Exception:
            return None
        if view is None:
            return None

        try:
            body = view.getActiveObject("pdbody")
        except Exception:
            body = None
        if body is not None:
            return body

        # A document with exactly one Body: activate it, like getBody() does.
        bodies = [o for o in doc.Objects if o.isDerivedFrom("PartDesign::Body")]
        if len(bodies) == 1:
            try:
                view.setActiveObject("pdbody", bodies[0])
            except Exception:
                pass
            return bodies[0]

        # Otherwise only commit to a body that contains the entire selection.
        target = None
        for o in sel:
            parent = o.getParentGeoFeatureGroup()
            if parent is None or not parent.isDerivedFrom("PartDesign::Body"):
                return None
            if target is None:
                target = parent
            elif target is not parent:
                return None
        return target

    @staticmethod
    def _outside_body(sel, body):
        group = set(body.Group)
        return [s for s in sel if s not in group]

    @staticmethod
    def _activate_design(doc, sel, body):
        outside = RibLoftCommand._outside_body(sel, body)
        if outside:
            FreeCAD.Console.PrintWarning(
                "RibLoft: %s not in body '%s'; linking them anyway "
                "(expect an out-of-scope link warning)\n"
                % (", ".join(o.Name for o in outside), body.Label))
        prev_tip = body.Tip
        rib = ribloft.makePartDesignRibLoft(doc, sel, body, label="RibLoft")
        FreeCAD.Console.PrintMessage(
            "RibLoft: added %s to body '%s' (%d solids)\n"
            % (rib.Name, body.Label, len(rib.Shape.Solids)))
        # PartDesign convention: show the new tip, hide the previous feature
        try:
            if prev_tip is not None and prev_tip.ViewObject is not None:
                prev_tip.ViewObject.Visibility = False
            if rib.ViewObject is not None:
                rib.ViewObject.Visibility = True
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RibLoft: could not update feature visibility (%s)\n" % exc)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(rib)

    @staticmethod
    def _activate_part(doc, sel):
        container = None
        for o in doc.Objects:
            group = getattr(o, "Group", None)
            if group is not None and sel[0] in group and \
                    hasattr(o, "Placement"):
                container = o
                break
        rib = ribloft.makeRibLoft(doc, sel, container=container)
        FreeCAD.Console.PrintMessage(
            "RibLoft: created %s (%d solids)\n"
            % (rib.Name, len(rib.Shape.Solids)))
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(rib)


FreeCADGui.addCommand("RibLoft_Create", RibLoftCommand())

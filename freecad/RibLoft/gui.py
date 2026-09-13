# SPDX-License-Identifier: MIT
# GUI wiring for RibLoft. Only imported from init_gui.py (i.e. with a GUI
# session); the document-restore path never touches this module.

import FreeCAD
import FreeCADGui

from freecad.RibLoft import ICONPATH
from freecad.RibLoft import ribloft
from freecad.RibLoft import taskpanel


class RibLoftCommand:
    """Create a RibLoft interactively, native-loft style.

    The feature is created right away and an interactive task panel opens:
    profiles are picked in the 3D view while the dialog is open (click adds,
    Ctrl+click removes) with a live transparent preview of the loft; all
    options are configurable from the panel. OK commits the transaction,
    Cancel aborts it (the feature never existed). Context-sensitive: with an
    active PartDesign Body the ribs are fused into that body's feature chain
    (additive, like an AdditiveLoft); without one a standalone Part feature
    holding the rib compound is created in the profiles' container.
    """

    def GetResources(self):
        return {
            "Pixmap": ICONPATH + "/ribloft.svg",
            "MenuText": "RibLoft",
            "ToolTip": "Loft corresponding wires of two or more multi-wire "
                       "profiles. Opens an interactive dialog: pick profiles "
                       "in the 3D view with a live preview; wires are paired "
                       "between profiles and corner-matched automatically, "
                       "so rotated or re-ordered sections do not produce "
                       "twisted lofts. With an active Body the ribs are "
                       "fused into it additively.",
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        sel = list(FreeCADGui.Selection.getSelection())
        candidates = [o for o in sel
                      if taskpanel.is_profile_candidate(o)]
        body = self._active_body(doc, sel)

        doc.openTransaction("Create RibLoft")
        try:
            prev_tip = body.Tip if body is not None else None
            if body is not None:
                rib = self._create_design(doc, candidates, body, prev_tip)
            else:
                rib = self._create_part(doc, candidates)
        except Exception:
            doc.abortTransaction()
            raise

        try:
            panel = taskpanel.RibLoftTaskPanel(doc, rib, body=body,
                                               creating=True)
            dialog = FreeCADGui.Control.showDialog(panel)
        except Exception:
            doc.abortTransaction()
            raise
        if dialog is not None:
            dialog.setAutoCloseOnTransactionChange(True)
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(doc.Name)

    @staticmethod
    def _create_design(doc, candidates, body, prev_tip):
        rib = ribloft.makePartDesignRibLoft(doc, candidates, body,
                                             recompute=False)
        outside = RibLoftCommand._outside_body(candidates, body)
        if outside:
            FreeCAD.Console.PrintWarning(
                "RibLoft: %s not in body '%s'; linking them anyway "
                "(expect an out-of-scope link warning)\n"
                % (", ".join(o.Name for o in outside), body.Label))
        # PartDesign convention while editing: show the new tip, hide the
        # previous feature (inside the transaction, so Cancel restores it).
        try:
            if prev_tip is not None and prev_tip.ViewObject is not None:
                prev_tip.ViewObject.Visibility = False
            if rib.ViewObject is not None:
                rib.ViewObject.Visibility = True
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RibLoft: could not update feature visibility (%s)\n" % exc)
        return rib

    @staticmethod
    def _create_part(doc, candidates):
        container = None
        for o in doc.Objects:
            group = getattr(o, "Group", None)
            if group is not None and candidates and candidates[0] in group \
                    and hasattr(o, "Placement"):
                container = o
                break
        return ribloft.makeRibLoft(doc, candidates, container=container,
                                    recompute=False)

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


FreeCADGui.addCommand("RibLoft_Create", RibLoftCommand())

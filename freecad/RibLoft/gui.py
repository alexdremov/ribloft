# SPDX-License-Identifier: MIT
# GUI wiring for RibLoft. Only imported from init_gui.py (i.e. with a GUI
# session); the document-restore path never touches this module.

import FreeCAD
import FreeCADGui

from freecad.RibLoft import ICONPATH
from freecad.RibLoft import ribloft


class RibLoftCommand:
    """Create a RibLoft from the selected profile objects."""

    def GetResources(self):
        return {
            "Pixmap": ICONPATH + "/ribloft.svg",
            "MenuText": "RibLoft",
            "ToolTip": "Loft corresponding wires of two or more multi-wire "
                       "profiles. Wires are paired between profiles and "
                       "corner-matched automatically, so rotated or "
                       "re-ordered sections do not produce twisted lofts. "
                       "Select the profiles in flow order.",
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

        container = None
        for o in doc.Objects:
            group = getattr(o, "Group", None)
            if group is not None and sel[0] in group and \
                    hasattr(o, "Placement"):
                container = o
                break

        rib = ribloft.makeRibLoft(doc, sel, container=container)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(rib)
        FreeCAD.Console.PrintMessage(
            "RibLoft: created %s (%d solids)\n"
            % (rib.Name, len(rib.Shape.Solids)))


FreeCADGui.addCommand("RibLoft_Create", RibLoftCommand())

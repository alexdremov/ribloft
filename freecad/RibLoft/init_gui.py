# SPDX-License-Identifier: MIT
# Workbench registration, loaded by FreeCAD on GUI start (modern package.xml
# convention; no InitGui.py needed).

import os

import FreeCADGui

from freecad.RibLoft import ICONPATH


class RibLoftWorkbench(FreeCADGui.Workbench):
    MenuText = "RibLoft"
    ToolTip = "Parametric lofts through corresponding wires of multi-wire profiles"
    Icon = os.path.join(ICONPATH, "ribloft.svg")

    def Initialize(self):
        from freecad.RibLoft import gui  # registers RibLoft_Create
        self.appendToolbar("RibLoft", ["RibLoft_Create"])
        self.appendMenu("RibLoft", ["RibLoft_Create"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(RibLoftWorkbench())

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


class _PartDesignToolbarInjector:
    """Appends RibLoft_Create to the PartDesign workbench's modeling toolbar.

    The manipulator runs for every workbench activation; workbenches without
    a toolbar of that name silently skip the request (see
    WorkbenchManipulatorPython::tryModifyToolBar).
    """

    def modifyToolBars(self):
        return [{"append": "RibLoft_Create",
                 "toolBar": "Part Design Modeling Features"}]


FreeCADGui.addWorkbenchManipulator(_PartDesignToolbarInjector())

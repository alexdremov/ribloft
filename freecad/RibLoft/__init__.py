"""RibLoft — parametric lofts through corresponding wires of multi-wire profiles."""

import os

ICONPATH = os.path.join(os.path.dirname(__file__), "resources", "icons")

__version__ = "0.3.0"

# Keep this package importable WITHOUT FreeCAD (the assign solver is used and
# unit-tested standalone). Documents store "freecad.RibLoft.ribloft" as the
# Proxy module; FreeCAD imports that submodule directly on document restore,
# so no eager import of the FreeCAD-dependent proxy is needed here.

# SPDX-License-Identifier: MIT
# Interactive RibLoft task panel — the native-loft-style frontend.
#
# The command creates the feature right away and opens this panel (like
# PartDesign does): profiles are picked in the 3D view while the dialog is
# open, every change recomputes the feature (transparent live preview), OK
# commits the transaction and Cancel aborts it, so a cancelled RibLoft never
# existed. Double-clicking an existing RibLoft reopens the panel in edit
# mode (property edits are undone by Cancel the same way).
#
# GUI-only module: imports FreeCADGui/Qt, never imported headless.

import FreeCAD
import FreeCADGui

from PySide import QtCore, QtGui, QtWidgets

from freecad.RibLoft import ribloft

# Currently open panel (lets tests and macros drive it programmatically).
ACTIVE_PANEL = None

_PREVIEW_TRANSPARENCY = 65


def is_profile_candidate(obj, rib=None):
    """Can `obj` be used as a RibLoft profile source?"""
    if obj is None or obj is rib:
        return False
    if not obj.isDerivedFrom("Part::Feature") or not hasattr(obj, "Shape"):
        return False
    # Solid features, bodies and datums hold derived/degenerate shapes, not
    # profile wires.
    if obj.isDerivedFrom("PartDesign::Feature"):
        return False
    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("Part::Datum"):
        return False
    return True


class _ProfileGate:
    """Selection gate: only profile objects are pickable while the panel is
    open (everything else shows the "not allowed" cursor)."""

    def __init__(self, rib):
        self.rib = rib

    def allow(self, doc, obj, sub):
        return is_profile_candidate(obj, self.rib)


def _error_text(obj):
    """Human-readable message for an object left in an error state."""
    try:
        txt = obj.getStatusString()
    except Exception:
        txt = ""
    if not txt or txt in ("Error", "Invalid"):
        txt = ", ".join(getattr(obj, "State", [])) or "recompute failed"
    return txt


class RibLoftTaskPanel:
    """Task dialog that creates/edits a RibLoft interactively.

    Implements the FreeCADGui task-dialog contract (``form``,
    ``getStandardButtons``, ``accept``/``reject``, ``autoClosedOn*``).
    Selection observation is always on while the dialog is open: a plain
    click in the 3D view adds the profile, Ctrl+click removes it, and the
    feature is recomputed after every change so the loft preview follows.
    """

    def __init__(self, doc, rib, body=None, creating=False):
        self.doc = doc
        self.rib = rib
        self.body = body
        self.creating = creating
        self._sources = list(rib.Sources)
        self._syncing = False       # ignore selection events we cause ourselves
        self._finished = False
        self._orig_transparency = None

        self._build_form()
        self._load_settings()
        self._sync_list()
        self._start_preview()
        self._start_selection_capture()
        self._update_preview()

        global ACTIVE_PANEL
        ACTIVE_PANEL = self

    # ------------------------------------------------------------------ form
    def _build_form(self):
        form = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(form)

        profiles = QtWidgets.QGroupBox("Profiles (flow order)", form)
        pv = QtWidgets.QVBoxLayout(profiles)
        self.list = QtWidgets.QListWidget(profiles)
        pv.addWidget(self.list)
        row = QtWidgets.QHBoxLayout()
        for text, tip, handler in (
                ("Up", "Move the selected profile one step up", self._on_up),
                ("Down", "Move the selected profile one step down", self._on_down),
                ("Remove", "Remove the selected profile", self._on_remove),
                ("Clear", "Remove all profiles", self._on_clear)):
            btn = QtWidgets.QToolButton(profiles)
            btn.setText(text)
            btn.setToolTip(tip)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        pv.addLayout(row)
        lay.addWidget(profiles)

        settings = QtWidgets.QGroupBox("Loft settings", form)
        grid = QtWidgets.QGridLayout(settings)

        def add_check(prop, text, tip, r):
            chk = QtWidgets.QCheckBox(text, settings)
            chk.setToolTip(tip)
            chk.toggled.connect(lambda v: self._set_prop(prop, v))
            grid.addWidget(chk, r, 0, 1, 2)
            return chk

        self.chk_ruled = add_check(
            "Ruled", "Ruled surface",
            "Straight ruling between sections instead of smooth B-splines", 0)
        self.chk_closed = add_check(
            "Closed", "Closed loft",
            "Close the loft by returning to the first profile", 1)
        self.chk_corners = add_check(
            "MatchCorners", "Match corners",
            "Rotate each wire's start vertex and winding to its neighbour's "
            "nearest corners before lofting; prevents twisted lofts", 2)

        lbl = QtWidgets.QLabel("Wire pairing", settings)
        self.combo_wirematch = QtWidgets.QComboBox(settings)
        self.combo_wirematch.addItems(ribloft.WIRE_MATCH_MODES)
        self.combo_wirematch.setToolTip(
            "How wires of consecutive profiles are paired: Optimal = minimum "
            "total centroid distance (Hungarian algorithm); Index = wire "
            "order as-is")
        self.combo_wirematch.currentTextChanged.connect(
            lambda v: self._set_prop("WireMatch", v))
        grid.addWidget(lbl, 3, 0)
        grid.addWidget(self.combo_wirematch, 3, 1)

        lbl = QtWidgets.QLabel("Max degree", settings)
        self.spin_maxdeg = QtWidgets.QSpinBox(settings)
        self.spin_maxdeg.setRange(2, 8)
        self.spin_maxdeg.setToolTip(
            "Maximum B-spline degree (smooth mode)")
        self.spin_maxdeg.valueChanged.connect(
            lambda v: self._set_prop("MaxDegree", int(v)))
        grid.addWidget(lbl, 4, 0)
        grid.addWidget(self.spin_maxdeg, 4, 1)

        self.chk_solid = add_check(
            "Solid", "Solid", "Build solids instead of shells", 5)
        self.chk_refine = add_check(
            "Refine", "Refine",
            "Remove redundant edges after fusing into the body", 6)
        if self.rib.isDerivedFrom("PartDesign::FeaturePython"):
            self.chk_solid.hide()   # PartDesign features always contribute solids
        else:
            self.chk_refine.hide()
        lay.addWidget(settings)

        self.status = QtWidgets.QLabel(form)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()
        self.form = form

    def _load_settings(self):
        """Push the object's current properties into the widgets (no
        recompute events — signals are blocked)."""
        rib = self.rib
        for w, prop in ((self.chk_ruled, "Ruled"), (self.chk_closed, "Closed"),
                        (self.chk_corners, "MatchCorners"),
                        (self.chk_solid, "Solid"), (self.chk_refine, "Refine")):
            w.blockSignals(True)
            w.setChecked(getattr(rib, prop))
            w.blockSignals(False)
        for w, prop in ((self.combo_wirematch, "WireMatch"),):
            w.blockSignals(True)
            w.setCurrentText(getattr(rib, prop))
            w.blockSignals(False)
        self.spin_maxdeg.blockSignals(True)
        self.spin_maxdeg.setValue(rib.MaxDegree)
        self.spin_maxdeg.blockSignals(False)
        self._update_enabled()

    def _update_enabled(self):
        self.spin_maxdeg.setEnabled(not self.rib.Ruled)

    # -------------------------------------------------- selection observation
    def _start_selection_capture(self):
        sel = FreeCADGui.Selection
        sel.addObserver(self, sel.ResolveMode.NoResolve)
        sel.addSelectionGate(_ProfileGate(self.rib), sel.ResolveMode.NoResolve)

    def _stop_selection_capture(self):
        try:
            sel = FreeCADGui.Selection
            sel.removeSelectionGate()
            sel.removeObserver(self)
        except Exception:
            pass

    def addSelection(self, doc_name, obj_name, sub_name, mousePos):
        if self._syncing:
            return
        try:
            obj = FreeCAD.getDocument(doc_name).getObject(obj_name)
        except Exception:
            return
        if not is_profile_candidate(obj, self.rib):
            FreeCADGui.Selection.removeSelection(doc_name, obj_name, sub_name)
            self._status("%s is not a usable profile (sketch or wire shape)"
                         % (obj.Label if obj else obj_name), error=True)
            return
        if any(s.Name == obj_name for s in self._sources):
            return
        self._sources.append(obj)
        self._sync_list()
        self._update_preview()

    def removeSelection(self, doc_name, obj_name, sub_name, mousePos=None):
        if self._syncing:
            return
        rest = [s for s in self._sources if s.Name != obj_name]
        if len(rest) != len(self._sources):
            self._sources = rest
            self._sync_list()
            self._update_preview()

    def clearSelection(self, doc_name):
        if self._syncing:
            return
        # Plain clicks clear the 3D selection first; the panel list is the
        # source of truth, so restore the highlights of the picked profiles.
        self._restore_highlights()

    def _restore_highlights(self):
        self._syncing = True
        try:
            sel = FreeCADGui.Selection
            for s in self._sources:
                if not sel.isSelected(s):
                    sel.addSelection(s)
        except Exception:
            pass
        self._syncing = False

    # ------------------------------------------------------------------ list
    def _current_source(self):
        row = self.list.currentRow()
        if 0 <= row < len(self._sources):
            return row
        return None

    def _sync_list(self):
        self.list.clear()
        for s in self._sources:
            text = s.Label
            try:
                n = len(s.Shape.Wires)
                text += "  (%d wire%s)" % (n, "" if n == 1 else "s")
            except Exception:
                pass
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, s.Name)
            try:
                item.setIcon(QtGui.QIcon(s.ViewObject.Icon))
            except Exception:
                pass
            self.list.addItem(item)

    def _on_up(self):
        i = self._current_source()
        if i and i > 0:
            self._sources[i - 1], self._sources[i] = \
                self._sources[i], self._sources[i - 1]
            self._sync_list()
            self.list.setCurrentRow(i - 1)
            self._update_preview()

    def _on_down(self):
        i = self._current_source()
        if i is not None and i + 1 < len(self._sources):
            self._sources[i + 1], self._sources[i] = \
                self._sources[i], self._sources[i + 1]
            self._sync_list()
            self.list.setCurrentRow(i + 1)
            self._update_preview()

    def _on_remove(self):
        i = self._current_source()
        if i is not None:
            self._sources.pop(i)
            self._sync_list()
            self._sync_highlights()
            self._update_preview()

    def _on_clear(self):
        self._sources = []
        self._sync_list()
        self._sync_highlights()
        self._update_preview()

    def _sync_highlights(self):
        """Make the 3D selection mirror the profile list exactly."""
        self._syncing = True
        try:
            sel = FreeCADGui.Selection
            names = {s.Name for s in self._sources}
            for o in sel.getSelection():
                if o.Name not in names and o.Document is self.doc:
                    sel.removeSelection(self.doc.Name, o.Name)
            for s in self._sources:
                if not sel.isSelected(s):
                    sel.addSelection(s)
        except Exception:
            pass
        self._syncing = False

    # --------------------------------------------------------------- preview
    def _start_preview(self):
        vobj = getattr(self.rib, "ViewObject", None)
        if vobj is None:
            return
        try:
            self._orig_transparency = vobj.Transparency
            vobj.Transparency = _PREVIEW_TRANSPARENCY
        except Exception:
            self._orig_transparency = None

    def _end_preview(self):
        if self._orig_transparency is None:
            return
        try:
            self.rib.ViewObject.Transparency = self._orig_transparency
        except Exception:
            pass
        self._orig_transparency = None

    def _set_prop(self, prop, value):
        setattr(self.rib, prop, value)
        self._update_enabled()
        self._update_preview()

    def _update_preview(self):
        rib = self.rib
        try:
            rib.Sources = list(self._sources)
        except Exception as exc:
            self._status(str(exc), error=True)
            return
        n = len(self._sources)
        if n < 2:
            self._status(
                "Pick profiles in the 3D view — click adds, Ctrl+click "
                "removes (%d of 2+ picked so far)" % n)
            return
        try:
            ok = rib.recompute()
        except Exception as exc:
            self._status("RibLoft: %s" % exc, error=True)
            return
        if not ok or "Invalid" in rib.State or "Error" in rib.State:
            self._status(_error_text(rib), error=True)
            return
        try:
            solids = len(rib.Shape.Solids)
        except Exception:
            solids = 0
        self._status("RibLoft preview: %d rib solid%s from %d profiles"
                     % (solids, "" if solids == 1 else "s", n))

    def _status(self, text, error=False):
        self.status.setText(text)
        # Empty stylesheet keeps the theme's own text colour for hints.
        self.status.setStyleSheet("QLabel { color : #a00000; }" if error else "")

    # ------------------------------------------------------- dialog contract
    def getStandardButtons(self):
        box = QtWidgets.QDialogButtonBox.StandardButton
        return int(box.Ok | box.Cancel)

    def accept(self):
        if len(self._sources) < 2:
            self._status("At least two profiles are needed — pick another "
                         "profile in the 3D view", error=True)
            return False
        self.rib.Sources = list(self._sources)
        try:
            ok = self.rib.recompute()
        except Exception as exc:
            self._status("RibLoft: %s" % exc, error=True)
            return False
        if not ok or "Invalid" in self.rib.State or "Error" in self.rib.State:
            self._status(_error_text(self.rib), error=True)
            return False
        self._finish(commit=True)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.rib)
        FreeCAD.Console.PrintMessage(
            "RibLoft: %s (%d profiles, %d solids)\n"
            % (self.rib.Name, len(self._sources),
               len(self.rib.Shape.Solids)))
        return True

    def reject(self):
        self._finish(commit=False)
        return True

    def autoClosedOnTransactionChange(self):
        # The transaction was committed/aborted elsewhere (e.g. user undo):
        # tear the panel down without touching transactions again.
        self._cleanup()

    def autoClosedOnDeletedDocument(self):
        self._cleanup()

    def _finish(self, commit):
        self._stop_selection_capture()
        self._end_preview()
        if commit:
            self.doc.commitTransaction()
        else:
            # Create mode: the feature never existed. Edit mode: property
            # edits are rolled back.
            self.doc.abortTransaction()
        self._cleanup()

    def _cleanup(self):
        if self._finished:
            return
        self._finished = True
        self._stop_selection_capture()
        self._end_preview()
        global ACTIVE_PANEL
        if ACTIVE_PANEL is self:
            ACTIVE_PANEL = None


def edit_ribloft(obj):
    """Open the edit dialog for an existing RibLoft (double-click entry)."""
    doc = obj.Document
    active = FreeCADGui.Control.activeTaskDialog()
    if active is not None:
        active.reject()
    doc.abortTransaction()  # close any stray auto-transaction (Assembly pattern)
    body = obj.getParentGeoFeatureGroup()
    doc.openTransaction("Edit RibLoft")
    try:
        panel = RibLoftTaskPanel(doc, obj, body=body, creating=False)
        dlg = FreeCADGui.Control.showDialog(panel)
    except Exception:
        doc.abortTransaction()
        raise
    dlg.setAutoCloseOnTransactionChange(True)
    dlg.setAutoCloseOnDeletedDocument(True)
    dlg.setDocumentName(doc.Name)
    return True

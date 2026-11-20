"""Mastercam-style bars: AutoCursor (X/Y/Z + fast point + snaps), the
per-command Ribbon bar (fields, locks, Apply and OK) and a status bar
(Cplane, depth, system axes)."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from . import snap as snapmod

LOCKED = "background-color:#ff7070; color:black;"


def fmt(v):
    return "%.4f" % v


def parse_number(text):
    """Number or FreeCAD expression with optional units ("2*3", "1in")."""
    text = text.strip()
    if not text:
        raise ValueError("empty")
    try:
        return float(text)
    except ValueError:
        return App.Units.Quantity(text).Value


class _EscFilter(QtCore.QObject):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.KeyPress and ev.key() == QtCore.Qt.Key_Escape:
            self.session.escape()
            return True
        return False


class AutoCursorBar(QtGui.QToolBar):
    def __init__(self, session):
        super().__init__("DG AutoCursor")
        self.setObjectName("DG_AutoCursor")
        self.session = session
        self.esc = _EscFilter(session)
        self.fields, self.locks = {}, {}
        for ax in "XYZ":
            b = QtGui.QToolButton()
            b.setText(ax)
            b.setCheckable(True)
            b.setToolTip("Lock %s: keep this coordinate while picking" % ax)
            e = QtGui.QLineEdit()
            e.setFixedWidth(90)
            e.setToolTip("%s coordinate (global). Type a value and press Enter to place a point." % ax)
            e.returnPressed.connect(session.submit_xyz)
            e.installEventFilter(self.esc)
            b.toggled.connect(lambda on, e=e: e.setStyleSheet(LOCKED if on else ""))
            self.addWidget(b)
            self.addWidget(e)
            self.fields[ax], self.locks[ax] = e, b
        self.addSeparator()
        self.fast = QtGui.QLineEdit()
        self.fast.setPlaceholderText("Fast point: x,y,z  Enter")
        self.fast.setToolTip("Type 2,2,3 and press Enter for global X2 Y2 Z3.\n"
                             "Two values (2,2) are taken on the Cplane at its depth.\n"
                             "Expressions and units work: 1in, 25.4/2")
        self.fast.setFixedWidth(170)
        self.fast.returnPressed.connect(self._fast)
        self.fast.installEventFilter(self.esc)
        self.addWidget(self.fast)
        self.addSeparator()
        # AutoCursor configuration
        cfg = QtGui.QToolButton()
        cfg.setText("AutoCursor")
        cfg.setToolTip("Choose what the cursor snaps to")
        cfg.setPopupMode(QtGui.QToolButton.InstantPopup)
        menu = QtGui.QMenu(cfg)
        for t in snapmod.SNAP_TYPES:
            a = menu.addAction(t)
            a.setCheckable(True)
            a.setChecked(session.snapper.enabled[t])
            a.toggled.connect(lambda on, t=t: session.snapper.enabled.__setitem__(t, on))
        cfg.setMenu(menu)
        self.addWidget(cfg)
        lab = QtGui.QLabel(" Only: ")
        self.addWidget(lab)
        self.only = QtGui.QComboBox()
        self.only.addItem("(all)")
        for t in snapmod.SNAP_TYPES:
            self.only.addItem(t)
        self.only.setToolTip("Selection filter: snap to one type only")
        self.only.currentIndexChanged.connect(self._only)
        self.addWidget(self.only)

    def _only(self, i):
        self.session.snapper.only = None if i <= 0 else self.only.currentText()

    def _fast(self):
        text = self.fast.text()
        self.fast.clear()
        self.session.submit_fast(text)

    def show_point(self, p):
        for ax, val in zip("XYZ", (p.x, p.y, p.z)):
            e = self.fields[ax]
            if not e.hasFocus() and not self.locks[ax].isChecked():
                e.setText(fmt(val))

    def apply_locks(self, p):
        p = App.Vector(p)
        for i, ax in enumerate("XYZ"):
            if self.locks[ax].isChecked():
                try:
                    p[i] = parse_number(self.fields[ax].text())
                except Exception:
                    pass
        return p

    def any_locked(self):
        return any(b.isChecked() for b in self.locks.values())

    def typed_point(self):
        vals = []
        for ax in "XYZ":
            vals.append(parse_number(self.fields[ax].text() or "0"))
        return App.Vector(*vals)

    def reset_locks(self):
        for b in self.locks.values():
            b.setChecked(False)

    def focus(self):
        self.fast.setFocus()


class RibbonBar(QtGui.QToolBar):
    """Rebuilt for each command from the tool's ribbon() spec:
    ("button", key, text, tip)
    ("toggle", key, text, checked, tip)
    ("number", key, label, value, lockable, tip)
    ("int", key, label, value, tip)
    ("choice", key, label, options, current, tip)
    """

    def __init__(self, session):
        super().__init__("DG Ribbon")
        self.setObjectName("DG_Ribbon")
        self.session = session
        self.esc = _EscFilter(session)
        self.action = None
        self.values, self.widgets, self.lockbtn = {}, {}, {}
        self.build(None)

    def build(self, tool):
        if self.action is not None:
            self.removeAction(self.action)
            self.container.deleteLater()
        self.container = QtGui.QWidget()
        lay = QtGui.QHBoxLayout(self.container)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(4)
        self.widgets, self.lockbtn = {}, {}
        self.title = QtGui.QLabel("<b>%s</b>" % (tool.title if tool else "Ribbon"))
        lay.addWidget(self.title)
        if tool is not None:
            for spec in tool.ribbon():
                self._add(lay, tool, spec)
        self.prompt_label = QtGui.QLabel("")
        self.prompt_label.setStyleSheet("color:#c06000;")
        lay.addSpacing(10)
        lay.addWidget(self.prompt_label)
        lay.addStretch(1)
        if tool is not None:
            ap = QtGui.QToolButton()
            ap.setText("+")
            ap.setToolTip("Apply: keep this entity and continue the command")
            ap.setStyleSheet("color:#109010; font-weight:bold; font-size:16px;")
            ap.clicked.connect(self.session.apply)
            ok = QtGui.QToolButton()
            ok.setText("✔")
            ok.setToolTip("OK: keep the entity and end the command (Esc does the same)")
            ok.setStyleSheet("color:#109010; font-weight:bold; font-size:16px;")
            ok.clicked.connect(self.session.ok)
            lay.addWidget(ap)
            lay.addWidget(ok)
        self.action = self.addWidget(self.container)

    def _add(self, lay, tool, spec):
        kind, key = spec[0], spec[1]
        if kind == "button":
            b = QtGui.QToolButton()
            b.setText(spec[2])
            b.setToolTip(spec[3] if len(spec) > 3 else "")
            b.clicked.connect(lambda _=False, k=key: self.session.ribbon_button(k))
            lay.addWidget(b)
            self.widgets[key] = b
        elif kind == "toggle":
            b = QtGui.QToolButton()
            b.setText(spec[2])
            b.setCheckable(True)
            b.setChecked(spec[3])
            b.setToolTip(spec[4] if len(spec) > 4 else "")
            b.toggled.connect(lambda on, k=key: self.session.ribbon_field(k, on))
            lay.addWidget(b)
            self.widgets[key] = b
        elif kind in ("number", "int"):
            label, value = spec[2], spec[3]
            lockable = kind == "number" and spec[4]
            tip = spec[5] if kind == "number" and len(spec) > 5 else (spec[4] if kind == "int" and len(spec) > 4 else "")
            if lockable:
                lb = QtGui.QToolButton()
                lb.setText(label)
                lb.setCheckable(True)
                lb.setToolTip("Lock %s" % label)
                lb.toggled.connect(lambda on, k=key, b=lb: self._lock(k, on, b))
                lay.addWidget(lb)
                self.lockbtn[key] = lb
            else:
                lay.addWidget(QtGui.QLabel(label))
            e = QtGui.QLineEdit(fmt(value) if kind == "number" else str(int(value)))
            e.setFixedWidth(80 if kind == "number" else 40)
            e.setToolTip(tip)
            e.installEventFilter(self.esc)
            e.returnPressed.connect(lambda k=key, e=e, i=(kind == "int"): self._num(k, e, i))
            lay.addWidget(e)
            self.widgets[key] = e
        elif kind == "choice":
            lay.addWidget(QtGui.QLabel(spec[2]))
            c = QtGui.QComboBox()
            c.addItems(spec[3])
            c.setCurrentText(spec[4])
            if len(spec) > 5:
                c.setToolTip(spec[5])
            c.currentTextChanged.connect(lambda t, k=key: self.session.ribbon_field(k, t))
            lay.addWidget(c)
            self.widgets[key] = c

    def _lock(self, key, on, btn):
        btn.setStyleSheet(LOCKED if on else "")
        self.session.ribbon_lock(key, on)

    def _num(self, key, edit, is_int):
        try:
            v = parse_number(edit.text())
            v = int(round(v)) if is_int else v
        except Exception:
            App.Console.PrintWarning("DirectGeo: not a number: %s\n" % edit.text())
            return
        self.session.ribbon_field(key, v)

    def set_value(self, key, value):
        w = self.widgets.get(key)
        if isinstance(w, QtGui.QLineEdit):
            if not w.hasFocus():
                w.setText(fmt(value) if isinstance(value, float) else str(value))
        elif isinstance(w, QtGui.QToolButton) and w.isCheckable():
            w.blockSignals(True)
            w.setChecked(bool(value))
            w.blockSignals(False)
        elif isinstance(w, QtGui.QComboBox):
            w.blockSignals(True)
            w.setCurrentText(value)
            w.blockSignals(False)

    def set_enabled(self, key, on):
        for w in (self.widgets.get(key), self.lockbtn.get(key)):
            if w is not None:
                w.setEnabled(on)

    def set_lock(self, key, on):
        b = self.lockbtn.get(key)
        if b is not None and b.isChecked() != on:
            b.setChecked(on)

    def prompt(self, text):
        self.prompt_label.setText(text)


class StatusBar(QtGui.QToolBar):
    def __init__(self, session):
        super().__init__("DG Status")
        self.setObjectName("DG_Status")
        self.session = session
        self.mode = QtGui.QToolButton()
        self.mode.setToolTip("Construction mode, click to switch.\n"
                             "2D: clicked and snapped points are put on the Cplane at Z depth,\n"
                             "so you can draw on top of other geometry by snapping to it.\n"
                             "3D: points stay exactly where they snap.\n"
                             "Typed coordinates are always used as typed.")
        self.mode.setStyleSheet("font-weight:bold;")
        self.mode.clicked.connect(lambda: session.set_mode_2d(not session.mode_2d))
        self.addWidget(self.mode)
        self.show_mode(session.mode_2d)
        self.addWidget(QtGui.QLabel(" Cplane: "))
        self.cplane = QtGui.QComboBox()
        self.cplane.addItems(["Top", "Front", "Right", "Back", "Left", "Bottom", "Gview", "Gnomon"])
        self.cplane.setToolTip("Construction plane: free picks land here; arcs, circles,\n"
                               "rectangles and polygons are drawn parallel to it.\n"
                               "Gview = plane facing the screen. Gnomon = plane of the transform gnomon.")
        self.cplane.textActivated.connect(session.set_cplane)
        self.addWidget(self.cplane)
        self.addWidget(QtGui.QLabel(" Z depth: "))
        self.depth = QtGui.QLineEdit("0.0000")
        self.depth.setFixedWidth(80)
        self.depth.setToolTip("Depth of the Cplane along its normal")
        self.depth.returnPressed.connect(self._depth)
        self.addWidget(self.depth)
        self.axes = QtGui.QToolButton()
        self.axes.setText("Axes (F9)")
        self.axes.setCheckable(True)
        self.axes.toggled.connect(lambda on: session.toggle_axes(on))
        self.addWidget(self.axes)

    def show_mode(self, on):
        self.mode.setText("MODE: 2D" if on else "MODE: 3D")

    def _depth(self):
        try:
            self.session.set_depth(parse_number(self.depth.text()))
        except Exception:
            pass

    def show_cplane(self, name, depth):
        self.cplane.blockSignals(True)
        self.cplane.setCurrentText(name)
        self.cplane.blockSignals(False)
        self.depth.setText(fmt(depth))


def main_window():
    return Gui.getMainWindow()

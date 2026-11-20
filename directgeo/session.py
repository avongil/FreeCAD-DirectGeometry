"""The running state of the workbench: Cplane, AutoCursor, bars, the active
tool and the 3D view event hookup."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore
from pivy import coin

from . import cplane as cplanemod
from . import snap as snapmod
from . import trackers, ui

_session = None


def get():
    global _session
    if _session is None:
        _session = Session()
    return _session


class Session:
    def __init__(self):
        self.cplane = cplanemod.CPlane()
        self.snapper = snapmod.Snapper()
        self.tool = None
        self.view = None
        self._cb = None
        self.preview = trackers.Tracker()
        self.marker = trackers.SnapMarker()
        self.axes = trackers.Axes()
        self.gnomon_frame = None    # (origin, rotation) of the last gnomon
        self.bars = None
        self.last = None            # last Snap
        self.mode_2d = True         # Mastercam construction mode: 2D or 3D

    # ------------------------------------------------------------- bars
    def show_bars(self):
        mw = ui.main_window()
        if self.bars is None:
            self.autocursor = ui.AutoCursorBar(self)
            self.ribbon = ui.RibbonBar(self)
            self.status = ui.StatusBar(self)
            mw.addToolBarBreak(QtCore.Qt.TopToolBarArea)
            mw.addToolBar(QtCore.Qt.TopToolBarArea, self.autocursor)
            mw.addToolBarBreak(QtCore.Qt.TopToolBarArea)
            mw.addToolBar(QtCore.Qt.TopToolBarArea, self.ribbon)
            mw.addToolBarBreak(QtCore.Qt.TopToolBarArea)
            mw.addToolBar(QtCore.Qt.TopToolBarArea, self.status)
            self.bars = (self.autocursor, self.ribbon, self.status)
        for b in self.bars:
            b.show()

    def hide_bars(self):
        self.end_tool()
        if self.bars:
            for b in self.bars:
                b.hide()

    def message(self, text):
        if self.bars:
            self.ribbon.prompt(text)
        try:
            ui.main_window().statusBar().showMessage(text)
        except Exception:
            pass

    # ------------------------------------------------------------ cplane
    def set_cplane(self, name):
        if name in cplanemod.STANDARD:
            self.cplane.set_standard(name)
        elif name == "Gview" and self.active_view():
            rot = self.active_view().getCameraOrientation()
            self.cplane.set_from_rotation(rot, App.Vector(0, 0, 0), "Gview")
        elif name == "Gnomon":
            if self.gnomon_frame is None:
                self.message("No gnomon yet: run Dynamic Transform first")
                self.status.show_cplane(self.cplane.name, self.cplane.depth)
                return
            o, rot = self.gnomon_frame
            self.cplane.set_from_rotation(rot, o, "Gnomon")
            self.cplane.depth = 0.0
        self.status.show_cplane(self.cplane.name, self.cplane.depth)
        self.message("Cplane: %s" % self.cplane.name)

    def set_depth(self, d):
        self.cplane.depth = d
        self.status.show_cplane(self.cplane.name, d)

    def toggle_axes(self, on=None):
        view = self.active_view()
        if view is None:
            return
        length = 120 * snapmod.Snapper.pixel_size(view, tuple(int(s / 2) for s in view.getSize()))
        state = self.axes.toggle(view, length)
        if self.bars:
            self.status.axes.blockSignals(True)
            self.status.axes.setChecked(state)
            self.status.axes.blockSignals(False)

    # ------------------------------------------------------------- tools
    @staticmethod
    def active_view():
        gd = Gui.ActiveDocument
        if gd is None:
            return None
        v = gd.ActiveView
        return v if hasattr(v, "getSceneGraph") else None

    def start_tool(self, tool):
        self.end_tool()
        view = self.active_view()
        if view is None or App.ActiveDocument is None:
            return
        self.show_bars()
        self.view = view
        self.tool = tool
        self._cb = view.addEventCallbackPivy(coin.SoEvent.getClassTypeId(), self._on_event)
        self.preview.attach(view)
        self.marker.attach(view)
        tool.begin(self)
        self.ribbon.build(tool)
        self.message(tool.prompt())
        self.autocursor.focus()

    def end_tool(self):
        tool, self.tool = self.tool, None
        if tool is not None:
            try:
                tool.end()
            except Exception as ex:
                App.Console.PrintError("DirectGeo: %s\n" % ex)
        if self.view is not None and self._cb is not None:
            try:
                self.view.removeEventCallbackPivy(coin.SoEvent.getClassTypeId(), self._cb)
            except Exception:
                pass
        self._cb = None
        self.preview.clear()
        self.preview.detach()
        self.marker.hide()
        self.marker.detach()
        self.view = None
        if self.bars:
            self.ribbon.build(None)
            self.autocursor.reset_locks()

    def request_end(self, tool):
        """End a tool after the current event has been processed."""
        tool.done = True
        QtCore.QTimer.singleShot(0, lambda: self.end_tool() if self.tool is tool else None)

    # buttons from the ribbon
    def apply(self):
        if self.tool:
            self.tool.apply()
            self._refresh_prompt()

    def ok(self):
        if self.tool:
            self.tool.finish()

    def escape(self):
        if self.tool:
            self.tool.escape()

    def ribbon_button(self, key):
        if self.tool:
            self.tool.on_button(key)
            self._refresh_prompt()

    def ribbon_field(self, key, val):
        if self.tool:
            try:
                self.tool.on_field(key, val)
            except Exception as ex:
                self.message(str(ex))
            self._refresh_prompt()

    def ribbon_lock(self, key, on):
        if self.tool:
            self.tool.locks[key] = on

    def _refresh_prompt(self):
        if self.tool:
            self.message(self.tool.prompt())
            self.autocursor.focus()

    # typed points
    def submit_xyz(self):
        try:
            p = self.autocursor.typed_point()
        except Exception as ex:
            self.message("Bad coordinate: %s" % ex)
            return
        self._typed(p)

    def submit_fast(self, text):
        text = text.strip()
        if not text:
            if self.tool:
                self.tool.on_enter()
                self._refresh_prompt()
            return
        parts = [s for s in text.replace(";", ",").split(",")]
        if len(parts) == 1:
            parts = text.split()
        try:
            vals = [ui.parse_number(s) for s in parts]
        except Exception:
            self.message("Fast point: type x,y,z (or x,y on the Cplane)")
            return
        if len(vals) == 3:
            p = App.Vector(*vals)
        elif len(vals) == 2:
            p = self.cplane.to_global(vals[0], vals[1])
        else:
            self.message("Fast point: type x,y,z (or x,y on the Cplane)")
            return
        self._typed(p)

    def _typed(self, p):
        if not self.tool:
            self.message("Start a command first (Create menu)")
            return
        self.autocursor.show_point(p)
        s = snapmod.Snap(p, "Typed")
        self.last = s
        self._run(self.tool.on_point, p, s)

    def _run(self, fn, *args):
        try:
            fn(*args)
        except Exception as ex:
            import traceback
            App.Console.PrintError("DirectGeo: %s\n%s" % (ex, traceback.format_exc()))
            self.message(str(ex))
        self._refresh_prompt()

    # ----------------------------------------------------------- events
    def _snap(self, pos):
        tool = self.tool
        s = self.snapper.snap(self.view, pos, self.cplane,
                              from_pt=tool.from_point(), exclude=tool.snap_exclude())
        if self.autocursor.any_locked():
            s.point = self.autocursor.apply_locks(s.point)
        s.snapped = s.point
        if self.mode_2d and tool.construction:
            # 2D mode: whatever was clicked or snapped lands on the Cplane at Z depth
            x, y, _ = self.cplane.to_local(s.point)
            s.point = self.cplane.to_global(x, y, 0.0)
        return s

    def set_mode_2d(self, on):
        self.mode_2d = on
        if self.bars:
            self.status.show_mode(on)
        self.message("MODE: 2D (points go onto the Cplane at Z depth)" if on
                     else "MODE: 3D (points stay where they snap)")

    def _show_marker(self, s):
        if s.kind in ("Cursor", "Typed"):
            self.marker.hide()
            return
        px = snapmod.Snapper.pixel_size(self.view, s.pos)
        up = App.Vector(self.view.getUpDirection()) if hasattr(self.view, "getUpDirection") else self.cplane.v
        off = (App.Vector(self.view.getViewDirection()).cross(up) * -12 + up * 10) * px
        self.marker.show(getattr(s, "snapped", s.point), snapmod.LABELS.get(s.kind, s.kind), off)

    def _on_event(self, cb):
        tool = self.tool
        if tool is None or self.view is None or tool.done:
            return
        ev = cb.getEvent()
        t = ev.getTypeId()
        try:
            if t.isDerivedFrom(coin.SoLocation2Event.getClassTypeId()):
                pos = tuple(ev.getPosition().getValue())
                if tool.uses_snap():
                    s = self._snap(pos)
                    self.last = s
                    self._show_marker(s)
                    self.autocursor.show_point(s.point)
                else:
                    s = snapmod.Snap(None, "Cursor", pos=pos)
                tool.on_move(s.point, s)
            elif t.isDerivedFrom(coin.SoMouseButtonEvent.getClassTypeId()):
                if ev.getButton() != coin.SoMouseButtonEvent.BUTTON1:
                    return
                if not tool.wants_clicks():
                    return
                cb.setHandled()
                if ev.getState() != coin.SoButtonEvent.DOWN:
                    return
                pos = tuple(ev.getPosition().getValue())
                s = self._snap(pos) if tool.uses_snap() else snapmod.Snap(None, "Cursor", pos=pos)
                self.last = s
                self._run(tool.on_point, s.point, s)
            elif t.isDerivedFrom(coin.SoKeyboardEvent.getClassTypeId()):
                if ev.getState() != coin.SoButtonEvent.DOWN:
                    return
                key = ev.getKey()
                if key == coin.SoKeyboardEvent.ESCAPE:
                    cb.setHandled()
                    self.escape()
                elif key in (coin.SoKeyboardEvent.RETURN, coin.SoKeyboardEvent.PAD_ENTER):
                    cb.setHandled()
                    self._run(tool.on_enter)
        except Exception as ex:
            import traceback
            App.Console.PrintError("DirectGeo event: %s\n%s" % (ex, traceback.format_exc()))

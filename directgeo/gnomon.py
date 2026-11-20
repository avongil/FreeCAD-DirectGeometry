"""Dynamic Transform (Mastercam X4 style) with an on-screen gnomon that
looks like FreeCAD's transform dragger: red/green/blue arrows to move along
an axis, small squares to move in a plane, arcs with ball handles to rotate,
and a centre ball to move freely to a snapped point.

Interaction is click - move - click: click a handle, move the mouse (the
AutoCursor still snaps), click again to place. The move or rotation stays
editable in the ribbon (dU/dV/dW, Angle) until the next one starts.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin

from . import entities, trackers
from .snap import Snapper
from .tools_base import Tool

V = App.Vector
RED, GREEN, BLUE = (0.85, 0.15, 0.15), (0.2, 0.8, 0.2), (0.2, 0.3, 0.95)
HILITE = (1.0, 0.85, 0.0)
SIZE_PX = 110


def _mat(color):
    m = coin.SoMaterial()
    m.diffuseColor = color
    m.emissiveColor = tuple(c * 0.35 for c in color)
    return m


def _rot_to(axis):
    """Rotation turning the Coin Y axis (cylinders, cones) onto axis 0/1/2."""
    r = coin.SoRotation()
    if axis == 0:
        r.rotation.setValue(coin.SbVec3f(0, 0, 1), -math.pi / 2)
    elif axis == 2:
        r.rotation.setValue(coin.SbVec3f(1, 0, 0), math.pi / 2)
    return r


class GnomonNode:
    """Coin geometry of the gnomon in unit size; scaled to pixels."""

    AXIS_COL = (RED, GREEN, BLUE)
    NAMES = ("U", "V", "W")

    def __init__(self):
        self.root = coin.SoSeparator()
        self.xf = coin.SoTransform()
        self.root.addChild(self.xf)
        self.handles = {}
        for i in range(3):
            self._arrow(i)
        for i in range(3):
            self._plane(i)
        for i in range(3):
            self._rotor(i)
        self._center()
        self.sg = None
        self.hot = None

    def _handle(self, name, color):
        sep = coin.SoSeparator()
        sep.setName(name)
        mat = _mat(color)
        sep.addChild(mat)
        self.root.addChild(sep)
        self.handles[name] = (sep, mat, color)
        return sep

    def _arrow(self, i):
        sep = self._handle("DG_T%d" % i, self.AXIS_COL[i])
        sep.addChild(_rot_to(i))
        t = coin.SoTranslation()
        t.translation = (0, 0.4, 0)
        sep.addChild(t)
        cyl = coin.SoCylinder()
        cyl.radius = 0.035
        cyl.height = 0.8
        sep.addChild(cyl)
        t2 = coin.SoTranslation()
        t2.translation = (0, 0.48, 0)
        sep.addChild(t2)
        cone = coin.SoCone()
        cone.bottomRadius = 0.09
        cone.height = 0.18
        sep.addChild(cone)
        t3 = coin.SoTranslation()
        t3.translation = (0, 0.2, 0)
        sep.addChild(t3)
        txt = coin.SoText2()
        txt.string = self.NAMES[i]
        sep.addChild(txt)

    def _plane(self, i):
        # plane i is normal to axis i: colored like that axis (as in FreeCAD)
        a, b = [(1, 2), (2, 0), (0, 1)][i]
        sep = self._handle("DG_P%d" % i, self.AXIS_COL[i])
        pos = [0.0, 0.0, 0.0]
        pos[a] = pos[b] = 0.3
        t = coin.SoTranslation()
        t.translation = tuple(pos)
        sep.addChild(t)
        cube = coin.SoCube()
        dims = [0.14, 0.14, 0.14]
        dims[i] = 0.02
        cube.width, cube.height, cube.depth = dims
        sep.addChild(cube)

    def _rotor(self, i):
        # rotation about axis i: quarter arc between the other two axes
        a, b = [(1, 2), (2, 0), (0, 1)][i]
        sep = self._handle("DG_R%d" % i, self.AXIS_COL[i])
        ds = coin.SoDrawStyle()
        ds.lineWidth = 3
        sep.addChild(ds)
        co = coin.SoCoordinate3()
        pts = []
        for k in range(25):
            ang = math.pi / 2 * k / 24
            p = [0.0, 0.0, 0.0]
            p[a] = 0.62 * math.cos(ang)
            p[b] = 0.62 * math.sin(ang)
            pts.append(tuple(p))
        co.point.setValues(0, len(pts), pts)
        sep.addChild(co)
        sep.addChild(coin.SoLineSet())
        t = coin.SoTranslation()
        mid = [0.0, 0.0, 0.0]
        mid[a] = mid[b] = 0.62 * math.cos(math.pi / 4)
        t.translation = tuple(mid)
        sep.addChild(t)
        sph = coin.SoSphere()
        sph.radius = 0.06
        sep.addChild(sph)

    def _center(self):
        sep = self._handle("DG_O", (0.95, 0.95, 0.95))
        sph = coin.SoSphere()
        sph.radius = 0.07
        sep.addChild(sph)

    # ---------------------------------------------------------------
    def attach(self, view):
        if self.sg is None:
            self.sg = view.getSceneGraph()
            self.sg.addChild(self.root)

    def detach(self):
        if self.sg is not None:
            self.sg.removeChild(self.root)
            self.sg = None

    def place(self, origin, rot, scale):
        self.xf.translation = (origin.x, origin.y, origin.z)
        q = rot.Q
        self.xf.rotation.setValue(q[0], q[1], q[2], q[3])
        self.xf.scaleFactor = (scale, scale, scale)

    def highlight(self, name):
        if name == self.hot:
            return
        if self.hot in self.handles:
            _, mat, col = self.handles[self.hot]
            mat.diffuseColor = col
            mat.emissiveColor = tuple(c * 0.35 for c in col)
        self.hot = name
        if name in self.handles:
            _, mat, _ = self.handles[name]
            mat.diffuseColor = HILITE
            mat.emissiveColor = HILITE

    def pick(self, view, pos):
        """Name of the handle under the screen position, or None."""
        if self.sg is None:
            return None
        rm = view.getViewer().getSoRenderManager()
        rp = coin.SoRayPickAction(rm.getViewportRegion())
        rp.setPoint(coin.SbVec2s(int(pos[0]), int(pos[1])))
        rp.setRadius(6)
        rp.setPickAll(True)
        rp.apply(rm.getSceneGraph())    # the full graph holds the camera
        pl = rp.getPickedPointList()
        found = []
        for i in range(pl.getLength()):
            path = pl[i].getPath()
            for k in range(path.getLength()):
                name = path.getNode(k).getName().getString()
                if name.startswith("DG_"):
                    found.append(name)
                    break
        if not found:
            return None
        # handles overlap when seen along an axis: centre ball first, then
        # arrows, planes and rotation arcs
        order = {"O": 0, "T": 1, "P": 2, "R": 3}
        return min(found, key=lambda n: order[n[3]])


class DynamicTransformTool(Tool):
    title = "Dynamic Transform"
    construction = False    # moves snap to true 3D points in either mode

    def setup(self):
        self.gn = GnomonNode()
        self.sel = []
        self.looks = {}
        self.state = "select"
        self.origin = V()
        self.rot = self.cp.rotation()
        self.mode = "Move"
        self.copies = 1
        self.reposition = False
        self.ang_step = 0.0
        self.dist_step = 0.0
        self.op = None          # last operation, editable from the ribbon
        self.drag = None
        self.copy_preview = trackers.Tracker(color=(0.35, 0.85, 1.0), width=2.0, on_top=False)
        self.sensor = None
        objs = [o for o in Gui.Selection.getSelection() if o.isDerivedFrom("Part::Feature")]
        if objs:
            self._take_selection(objs)

    def ribbon(self):
        return [
            ("button", "done_sel", "End Selection", "Use the selected entities"),
            ("choice", "mode", "", ["Move", "Copy"], "Move", "Move the entities or make copies"),
            ("int", "copies", "Copies", 1, "Number of copies (Copy mode)"),
            ("toggle", "reposition", "Gnomon Only", False,
             "Handles move/rotate the gnomon without the geometry (to reposition or re-orient it)"),
            ("number", "du", "dU", 0.0, False, "Move along the gnomon U axis (edits the last move)"),
            ("number", "dv", "dV", 0.0, False, "Move along V (edits the last move)"),
            ("number", "dw", "dW", 0.0, False, "Move along W (edits the last move)"),
            ("number", "angle", "Angle", 0.0, False, "Rotation angle (edits the last rotation)"),
            ("number", "astep", "Angle Step", 0.0, False, "Snap rotations to this step (0 = free)"),
            ("number", "dstep", "Dist Step", 0.0, False, "Snap free moves to this step (0 = free)"),
            ("button", "align", "Align to Cplane", "Orient the gnomon like the current Cplane"),
            ("button", "tocplane", "Cplane = Gnomon", "Make the gnomon plane (U,V) the construction plane"),
        ]

    def prompt(self):
        if self.state == "select":
            return "Select entities, then press Enter or End Selection"
        if self.state == "place":
            return "Pick the gnomon origin (Enter = center of the selection)"
        if self.state == "drag":
            return "Move the mouse and click to place (Esc cancels this move)"
        return "Click a gnomon handle: arrow = move on axis, square = move on plane, " \
               "arc = rotate, ball = move to a point"

    # ---------------------------------------------------------- states
    def uses_snap(self):
        return self.state != "select"

    def wants_clicks(self):
        return self.state != "select"

    def snap_exclude(self):
        return list(self.sel) if self.state == "drag" and self.mode == "Move" else []

    def _take_selection(self, objs):
        self.sel = objs
        self.state = "place"
        Gui.Selection.clearSelection()
        for o in objs:
            self.looks[o.Name] = entities.get_look(o)
            entities.style(o, entities.LIVE)

    def on_enter(self):
        if self.state == "select":
            objs = [o for o in Gui.Selection.getSelection() if o.isDerivedFrom("Part::Feature")]
            if not objs:
                self.s.message("Nothing selected")
                return
            self._take_selection(objs)
        elif self.state == "place":
            bb = None
            for o in self.sel:
                b = o.Shape.BoundBox
                if bb is None:
                    bb = b
                else:
                    bb.add(b)
            self._show_gnomon(bb.Center if bb else V())

    def on_button(self, key):
        if key == "done_sel":
            self.on_enter()
        elif key == "align":
            self.rot = self.cp.rotation()
            self._place_node()
        elif key == "tocplane":
            self.s.gnomon_frame = (V(self.origin), App.Rotation(self.rot))
            self.s.set_cplane("Gnomon")

    def on_field(self, key, val):
        if key == "mode":
            self.mode = val
        elif key == "copies":
            self.copies = max(1, int(val))
        elif key == "reposition":
            self.reposition = val
        elif key == "astep":
            self.ang_step = max(0.0, val)
        elif key == "dstep":
            self.dist_step = max(0.0, val)
        elif key in ("du", "dv", "dw"):
            if self.op is None or self.op["kind"] != "T":
                return
            loc = list(self.op["local"])
            loc["uvw".index(key[1])] = val
            self._redo_op(("T", tuple(loc)))
        elif key == "angle":
            if self.op is None or self.op["kind"] != "R":
                return
            self._redo_op(("R", val))

    # ------------------------------------------------------- gnomon
    def _axes(self, rot=None):
        r = rot or self.rot
        return [r.multVec(V(1, 0, 0)), r.multVec(V(0, 1, 0)), r.multVec(V(0, 0, 1))]

    def _scale(self):
        view = self.s.view
        try:
            pos = view.getPointOnScreen(self.origin)
            return SIZE_PX * Snapper.pixel_size(view, (int(pos[0]), int(pos[1])))
        except Exception:
            return SIZE_PX * Snapper.pixel_size(view, (0, 0))

    def _place_node(self, origin=None, rot=None):
        self.gn.place(origin or self.origin, rot or self.rot, self._scale())

    def _show_gnomon(self, origin):
        self.origin = V(origin)
        self.state = "idle"
        self.gn.attach(self.s.view)
        self._place_node()
        self.s.gnomon_frame = (V(self.origin), App.Rotation(self.rot))
        try:
            self.sensor = coin.SoNodeSensor(lambda *a: self._place_node(*self._live_frame()), None)
            self.sensor.attach(self.s.view.getCameraNode())
        except Exception:
            self.sensor = None

    def _live_frame(self):
        if self.drag and self.drag.get("frame"):
            return self.drag["frame"]
        return self.origin, self.rot

    # ---------------------------------------------------------- math
    def _ray(self, pos):
        return Snapper.ray(self.s.view, pos)

    @staticmethod
    def _ray_axis_param(p0, d, o, a):
        w = p0 - o
        b = d.dot(a)
        den = 1 - b * b
        if den < 1e-6:
            return None
        return (a.dot(w) - b * d.dot(w)) / den

    @staticmethod
    def _ray_plane(p0, d, o, n):
        den = d.dot(n)
        if abs(den) < 1e-9:
            return None
        return p0 + d * ((o - p0).dot(n) / den)

    def _step(self, v, step):
        return round(v / step) * step if step > 0 else v

    def _drag_value(self, snap):
        """Local translation (u,v,w) or rotation angle for the current drag."""
        h = self.drag["handle"]
        o = self.origin
        ax = self._axes()
        p0, d = self._ray(snap.pos)
        geo = snap.is_geometry
        if h == "DG_O":
            delta = snap.point - o
            return "T", tuple(delta.dot(a) for a in ax)
        k = int(h[-1])
        if h.startswith("DG_T"):
            a = ax[k]
            if geo:
                t = (snap.point - o).dot(a)
            else:
                t = self._ray_axis_param(p0, d, o, a)
                if t is None:
                    return None
                t = self._step(t - self.drag["t0"], self.dist_step)
            loc = [0.0, 0.0, 0.0]
            loc[k] = t
            return "T", tuple(loc)
        if h.startswith("DG_P"):
            n = ax[k]
            q = (snap.point - n * (snap.point - o).dot(n)) if geo else self._ray_plane(p0, d, o, n)
            if q is None:
                return None
            delta = q - o if geo else q - self.drag["q0"]
            loc = [delta.dot(a) for a in ax]
            loc[k] = 0.0
            if not geo:
                loc = [self._step(x, self.dist_step) for x in loc]
            return "T", tuple(loc)
        # rotation about axis k
        n = ax[k]
        q = (snap.point - n * (snap.point - o).dot(n)) if geo else self._ray_plane(p0, d, o, n)
        if q is None:
            return None
        v0 = self.drag["v0"]
        v1 = q - o
        if v1.Length < 1e-9:
            return None
        ang = math.degrees(math.atan2(v0.cross(v1).dot(n), v0.dot(v1)))
        return "R", self._step(ang, self.ang_step)

    def _matrix(self, value, origin=None, rot=None):
        origin = origin or self.origin
        ax = self._axes(rot)
        kind, val = value
        if kind == "T":
            vec = ax[0] * val[0] + ax[1] * val[1] + ax[2] * val[2]
            return App.Placement(vec, App.Rotation())
        axis = ax[self.op_axis]
        return App.Placement(V(), App.Rotation(axis, val), origin)

    # ---------------------------------------------------------- events
    def on_move(self, p, snap):
        if self.state == "idle":
            self.gn.highlight(self.gn.pick(self.s.view, snap.pos))
        elif self.state == "drag":
            value = self._drag_value(snap)
            if value is None:
                return
            self.drag["value"] = value
            self._apply_preview(value)
            self._show_value(value)

    def on_point(self, p, snap):
        if self.state == "place":
            self._show_gnomon(p)
            return
        if self.state == "idle":
            h = self.gn.pick(self.s.view, snap.pos)
            if h is None:
                return
            self._start_drag(h, snap)
            return
        if self.state == "drag":
            value = self._drag_value(snap) or self.drag.get("value")
            if value is None:
                return
            self._finish_drag(value)

    def _start_drag(self, h, snap):
        self._close_op()
        o = self.origin
        ax = self._axes()
        p0, d = self._ray(snap.pos)
        self.drag = {"handle": h, "value": None}
        if h.startswith("DG_T"):
            k = int(h[-1])
            t0 = self._ray_axis_param(p0, d, o, ax[k])
            self.drag["t0"] = t0 if t0 is not None else 0.0
        elif h.startswith("DG_P"):
            k = int(h[-1])
            self.drag["q0"] = self._ray_plane(p0, d, o, ax[k]) or V(o)
        elif h.startswith("DG_R"):
            k = int(h[-1])
            q = self._ray_plane(p0, d, o, ax[k])
            v0 = (q - o) if q is not None else ax[(k + 1) % 3]
            if v0.Length < 1e-9:
                v0 = ax[(k + 1) % 3]
            self.drag["v0"] = v0
        self.op_axis = int(h[-1]) if h.startswith("DG_R") else 0
        self.gn.highlight(h)
        self.state = "drag"
        self.orig_pl = {o.Name: App.Placement(o.Placement) for o in self.sel}
        if not self.reposition:
            self.doc.openTransaction("Dynamic Transform")
            self._txn = True
            if self.mode == "Copy":
                self.copy_preview.attach(self.s.view)

    def _apply_preview(self, value):
        pl = self._matrix(value)
        frame = (pl.multVec(self.origin), pl.Rotation.multiply(self.rot))
        self.drag["frame"] = frame
        self.gn.place(frame[0], frame[1], self._scale())
        if self.reposition:
            return
        if self.mode == "Move":
            for o in self.sel:
                o.Placement = pl.multiply(self.orig_pl[o.Name])
        else:
            shapes = []
            step = App.Placement()
            for _ in range(self.copies):
                step = pl.multiply(step)
                for o in self.sel:
                    sh = o.Shape.copy()
                    sh.Placement = step.multiply(sh.Placement)
                    shapes.append(sh)
            self.copy_preview.set_shapes(shapes)

    def _finish_drag(self, value):
        self.drag = None
        self.state = "idle"
        self.copy_preview.clear()
        self.copy_preview.detach()
        if self.reposition:
            pl = self._matrix(value)
            self.origin = pl.multVec(self.origin)
            self.rot = pl.Rotation.multiply(self.rot)
            self._place_node()
            self.s.gnomon_frame = (V(self.origin), App.Rotation(self.rot))
            self._show_value(value)
            return
        self.op = {"kind": value[0], "start_origin": V(self.origin), "start_rot": App.Rotation(self.rot),
                   "axis": self.op_axis, "orig_pl": dict(self.orig_pl), "sel": list(self.sel),
                   "created": []}
        self._do_op(value)

    def _do_op(self, value):
        op = self.op
        op["kind"] = value[0]
        if value[0] == "T":
            op["local"] = value[1]
        else:
            op["angle"] = value[1]
        self.op_axis = op["axis"]
        pl = self._matrix(value, op["start_origin"], op["start_rot"])
        if self.mode == "Move" and not op["created"]:
            for o in op["sel"]:
                if entities.alive(o):
                    o.Placement = pl.multiply(op["orig_pl"][o.Name])
            new_sel = op["sel"]
        else:
            created = []
            step = App.Placement()
            for _ in range(self.copies):
                step = pl.multiply(step)
                for o in op["sel"]:
                    if not entities.alive(o):
                        continue
                    sh = o.Shape.copy()
                    sh.Placement = step.multiply(sh.Placement)
                    new = entities.make(sh, live=True)
                    self.looks[new.Name] = self.looks.get(o.Name, {})
                    created.append(new)
            op["created"] = created
            op["copy"] = True
            for o in op["sel"]:
                self._restore_look(o)
            new_sel = created[-len(op["sel"]):] if created else op["sel"]
        self.doc.recompute()
        self.sel = new_sel
        self.origin = pl.multVec(op["start_origin"])
        self.rot = pl.Rotation.multiply(op["start_rot"])
        self._place_node()
        self.s.gnomon_frame = (V(self.origin), App.Rotation(self.rot))
        self._show_value(value)

    def _redo_op(self, value):
        op = self.op
        if op.get("copy"):
            for o in op["created"]:
                if entities.alive(o):
                    self.doc.removeObject(o.Name)
            op["created"] = []
        self._do_op(value)

    def _show_value(self, value):
        if value[0] == "T":
            for k, v in zip(("du", "dv", "dw"), value[1]):
                self.set_field(k, float(v))
        else:
            self.set_field("angle", float(value[1]))

    def _close_op(self):
        if self.op is not None:
            for o in self.op.get("created", []):
                if o not in self.sel:
                    self._restore_look(o)
        self.op = None
        self.close_txn()

    def _restore_look(self, o):
        """Give an entity back its own display settings (or a copy its source's)."""
        if not entities.alive(o):
            return
        look = self.looks.get(o.Name)
        if look:
            entities.set_look(o, look)
        else:
            entities.style(o, entities.DONE)

    def _cancel_drag(self):
        if self.drag is None:
            return
        if not self.reposition and self.mode == "Move":
            for o in self.sel:
                if entities.alive(o):
                    o.Placement = self.orig_pl[o.Name]
        self.drag = None
        self.state = "idle"
        self.copy_preview.clear()
        self.copy_preview.detach()
        if self._txn:
            self.doc.abortTransaction()
            self._txn = False
        self._place_node()

    # ------------------------------------------------------- end
    def escape(self):
        if self.state == "drag":
            self._cancel_drag()
            return
        self.finish()

    def apply(self):
        self._close_op()

    def commit(self):
        self._close_op()

    def cleanup(self):
        if self.state == "drag":
            self._cancel_drag()
        self._close_op()
        for o in self.sel:
            self._restore_look(o)
        if self.sensor is not None:
            try:
                self.sensor.detach()
            except Exception:
                pass
            self.sensor = None
        self.copy_preview.detach()
        self.gn.detach()

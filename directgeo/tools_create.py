"""Create commands: points, lines, circles/arcs, rectangles, polygons."""

import math

import FreeCAD as App
import Part

from . import geom
from .tools_base import Tool

V = App.Vector


# ------------------------------------------------------------------ point
class PointTool(Tool):
    title = "Point Position"

    def ribbon(self):
        return [("button", "edit", "Edit Point", "Click, then pick a new location for the live point")]

    def prompt(self):
        if self.editing:
            return "Pick the new location of the live point"
        return "Sketch a point, or type x,y,z and press Enter"

    def on_point(self, p, snap):
        if self.editing and self.live:
            self.set_live([Part.Vertex(p)])
            self.editing = None
            return
        self.commit()
        self.set_live([Part.Vertex(p)])


# ------------------------------------------------------------------- line
class LineTool(Tool):
    title = "Line Endpoints"

    def setup(self):
        self.p1 = None
        self.a = self.b = None
        self.multi = False
        self.horiz = self.vert = False
        self.tangent = False
        self.tan_first = None
        self.length = 1.0
        self.angle = 0.0

    def ribbon(self):
        return [
            ("button", "edit1", "Edit P1", "Pick a new first endpoint for the live line"),
            ("button", "edit2", "Edit P2", "Pick a new second endpoint for the live line"),
            ("toggle", "multi", "Multi", False, "Chain lines: each end starts the next line"),
            ("number", "length", "Length", self.length, True, "Length (Enter edits the live line; lock to constrain)"),
            ("number", "angle", "Angle", self.angle, True, "Angle in the Cplane, CCW positive"),
            ("toggle", "horiz", "Horizontal", False, "Force horizontal (Cplane X)"),
            ("toggle", "vert", "Vertical", False, "Force vertical (Cplane Y)"),
            ("toggle", "tangent", "Tangent", False, "Pick two circles/arcs to get the line tangent to both"),
        ]

    def prompt(self):
        if self.editing:
            return "Pick the new %s endpoint" % ("first" if self.editing == "edit1" else "second")
        if self.tangent:
            return "Select the second circle/arc" if self.tan_first else "Select the first circle/arc"
        return "Specify the second endpoint" if self.p1 is not None else "Specify the first endpoint"

    def from_point(self):
        return self.p1

    def reset(self):
        self.p1 = None
        self.tan_first = None

    def constrain(self, p1, p):
        cp = self.cp
        d = p - p1
        if self.horiz:
            d = cp.u * d.dot(cp.u)
        elif self.vert:
            d = cp.v * d.dot(cp.v)
        if self.locks.get("angle"):
            dirv = cp.direction(self.angle)
            t = d.dot(dirv)
            if self.locks.get("length"):
                t = self.length if t >= 0 else -self.length
            return p1 + dirv * t
        if self.locks.get("length") and d.Length > 1e-12:
            return p1 + V(d).normalize() * self.length
        return p1 + d

    def _show_dims(self, a, b):
        d = b - a
        if not self.locks.get("length"):
            self.length = d.Length
            self.set_field("length", self.length)
        if not self.locks.get("angle"):
            self.angle = self.cp.angle_of(d)
            self.set_field("angle", self.angle)

    def on_move(self, p, snap):
        if self.p1 is not None and not self.editing and p is not None:
            b = self.constrain(self.p1, p)
            self.preview([geom.line(self.p1, b)])
            self._show_dims(self.p1, b)

    def _make(self, a, b):
        if (b - a).Length < 1e-9:
            return False
        self.commit()
        self.a, self.b = a, b
        self.set_live([geom.line(a, b)])
        self._show_dims(a, b)
        return True

    def on_point(self, p, snap):
        if self.editing and self.live:
            if self.editing == "edit1":
                self.a = p
            else:
                self.b = p
            self.editing = None
            self.set_live([geom.line(self.a, self.b)])
            self._show_dims(self.a, self.b)
            return
        if self.tangent:
            e = snap.edge
            if e is None or not geom.is_circle(e):
                self.s.message("Select a circle or arc")
                return
            if self.tan_first is None:
                self.tan_first = (e, snap.hit or p)
                return
            res = geom.circle_circle_tangent(self.tan_first[0], self.tan_first[1], e, snap.hit or p)
            self.tan_first = None
            if res is None:
                self.s.message("No tangent line exists for these circles")
                return
            self._make(*res)
            return
        if self.p1 is None:
            self.commit()
            if self.locks.get("length") and self.locks.get("angle"):
                self._make(p, p + self.cp.direction(self.angle) * self.length)
                return
            self.p1 = p
            return
        b = self.constrain(self.p1, p)
        if self._make(self.p1, b):
            self.p1 = b if self.multi else None
            self.clear_preview()

    def on_field(self, key, val):
        if key == "multi":
            self.multi = val
        elif key == "horiz":
            self.horiz = val
            if val:
                self.vert = False
                self.set_field("vert", False)
        elif key == "vert":
            self.vert = val
            if val:
                self.horiz = False
                self.set_field("horiz", False)
        elif key == "tangent":
            self.tangent = val
            self.tan_first = None
        elif key == "length":
            self.length = val
            if self.live and self.p1 is None or (self.live and self.multi):
                d = self.b - self.a
                if d.Length > 1e-12:
                    self.b = self.a + V(d).normalize() * val
                    self.set_live([geom.line(self.a, self.b)])
                    if self.multi:
                        self.p1 = self.b
        elif key == "angle":
            self.angle = val
            if self.live and (self.p1 is None or self.multi):
                L = (self.b - self.a).Length
                self.b = self.a + self.cp.direction(val) * L
                self.set_live([geom.line(self.a, self.b)])
                if self.multi:
                    self.p1 = self.b


# --------------------------------------------------------------- parallel
class ParallelTool(Tool):
    title = "Line Parallel"

    def setup(self):
        self.base = None
        self.side = None
        self.dist = 1.0

    def ribbon(self):
        return [("number", "dist", "Distance", self.dist, True,
                 "Distance between the lines (Enter edits the live line)")]

    def prompt(self):
        return "Select the side for the parallel line" if self.base else "Select a line"

    def reset(self):
        self.base = None

    def _offset(self, p):
        e = self.base
        a = e.Vertexes[0].Point
        b = e.Vertexes[-1].Point
        d = (b - a).normalize()
        w = (p - a) - d * (p - a).dot(d)
        n = self.cp.n
        if abs(d.dot(n)) < 0.99:
            w = w - n * w.dot(n)
        return a, b, w

    def _build(self, a, b, side, dist):
        return geom.line(a + side * dist, b + side * dist)

    def on_move(self, p, snap):
        if self.base is None or p is None:
            return
        a, b, w = self._offset(p)
        if w.Length < 1e-9:
            return
        dist = self.dist if self.locks.get("dist") else w.Length
        if not self.locks.get("dist"):
            self.set_field("dist", dist)
        self.preview([self._build(a, b, V(w).normalize(), dist)])

    def on_point(self, p, snap):
        if self.base is None:
            e = snap.edge
            if e is None or not geom.is_line(e):
                self.s.message("Select a line")
                return
            self.commit()
            self.base = e
            return
        a, b, w = self._offset(p)
        if w.Length < 1e-9:
            return
        self.side = V(w).normalize()
        if not self.locks.get("dist"):
            self.dist = w.Length
        self.ends = (a, b)
        self.set_live([self._build(a, b, self.side, self.dist)])
        self.base = None
        self.clear_preview()

    def on_field(self, key, val):
        if key == "dist":
            self.dist = val
            if self.live and self.side is not None:
                self.set_live([self._build(self.ends[0], self.ends[1], self.side, val)])


# ------------------------------------------------------------------ circle
class CircleTool(Tool):
    title = "Circle Center Point"

    def setup(self):
        self.center = None
        self.c = None
        self.r = 1.0

    def ribbon(self):
        return [
            ("button", "editc", "Edit Center", "Pick a new center for the live circle"),
            ("number", "radius", "Radius", self.r, True, "Radius"),
            ("number", "diameter", "Diameter", self.r * 2, True, "Diameter"),
        ]

    def prompt(self):
        if self.editing:
            return "Pick the new center"
        return "Enter the radius point" if self.center is not None else "Enter the center point"

    def reset(self):
        self.center = None

    def snap_exclude(self):
        return list(self.live) if self.editing else []

    def _radius_to(self, p):
        d = p - self.center
        return math.sqrt(max(d.Length ** 2 - d.dot(self.cp.n) ** 2, 0.0))

    def _locked(self):
        return self.locks.get("radius") or self.locks.get("diameter")

    def _show(self, r):
        self.r = r
        self.set_field("radius", r)
        self.set_field("diameter", 2 * r)

    def on_move(self, p, snap):
        if self.center is not None and p is not None and not self._locked():
            r = self._radius_to(p)
            if r > 1e-9:
                self.preview([geom.circle(self.center, r, self.cp)])
                self._show(r)

    def on_point(self, p, snap):
        if self.editing == "editc" and self.live:
            self.c = p
            self.editing = None
            self.set_live([geom.circle(self.c, self.r, self.cp)])
            return
        if self.center is None:
            self.commit()
            if self._locked():
                self.c = p
                self.set_live([geom.circle(p, self.r, self.cp)])
                return
            self.center = p
            return
        r = self._radius_to(p)
        if r < 1e-9:
            return
        self._show(r)
        self.c = self.center
        self.set_live([geom.circle(self.c, r, self.cp)])
        self.center = None
        self.clear_preview()

    def on_field(self, key, val):
        if key in ("radius", "diameter"):
            r = val if key == "radius" else val / 2.0
            if r <= 0:
                return
            self._show(r)
            if self.live:
                self.set_live([geom.circle(self.c, r, self.cp)])
            elif self.center is not None:
                # typed radius after the center: create it right away
                self.c = self.center
                self.center = None
                self.clear_preview()
                self.set_live([geom.circle(self.c, r, self.cp)])


# --------------------------------------------------------------- arc polar
class ArcPolarTool(Tool):
    title = "Arc Polar"

    def setup(self):
        self.step = 0
        self.c = None
        self.r = 1.0
        self.a1 = 0.0
        self.a2 = 90.0

    def ribbon(self):
        return [
            ("button", "editc", "Edit Center", "Pick a new center for the live arc"),
            ("number", "radius", "Radius", self.r, True, "Radius"),
            ("number", "diameter", "Diameter", self.r * 2, True, "Diameter"),
            ("number", "start", "Start", self.a1, False, "Start angle, CCW from Cplane X"),
            ("number", "end", "End", self.a2, False, "End angle, CCW from Cplane X"),
            ("button", "flip", "Flip", "Use the complement of the arc"),
        ]

    def prompt(self):
        if self.editing:
            return "Pick the new center"
        return ["Enter the center point", "Enter the start point (sets radius and start angle)",
                "Enter the end point (arcs are counter-clockwise)"][self.step]

    def reset(self):
        self.step = 0

    def _locked(self):
        return self.locks.get("radius") or self.locks.get("diameter")

    def _build(self):
        return geom.arc_polar(self.c, self.r, self.a1, self.a2, self.cp)

    def _show(self):
        for k, v in (("radius", self.r), ("diameter", 2 * self.r), ("start", self.a1), ("end", self.a2)):
            self.set_field(k, v)

    def on_move(self, p, snap):
        if p is None or self.step == 0:
            return
        d = self.cp.flatten(p, self.c) - self.c
        if d.Length < 1e-9:
            return
        if self.step == 1:
            r = self.r if self._locked() else d.Length
            self.preview([geom.line(self.c, self.c + V(d).normalize() * r),
                          geom.circle(self.c, r, self.cp)])
        else:
            self.a2 = self.cp.angle_of(d)
            self.preview([geom.arc_polar(self.c, self.r, self.a1, self.a2, self.cp)])
            self._show()

    def on_point(self, p, snap):
        if self.editing == "editc" and self.live:
            self.c = p
            self.editing = None
            self.set_live([self._build()])
            return
        if self.step == 0:
            self.commit()
            self.c = p
            self.step = 1
            return
        d = self.cp.flatten(p, self.c) - self.c
        if d.Length < 1e-9:
            return
        if self.step == 1:
            if not self._locked():
                self.r = d.Length
            self.a1 = self.cp.angle_of(d)
            self.step = 2
            self._show()
            return
        self.a2 = self.cp.angle_of(d)
        self.set_live([self._build()])
        self._show()
        self.step = 0
        self.clear_preview()

    def on_field(self, key, val):
        if key == "radius" and val > 0:
            self.r = val
        elif key == "diameter" and val > 0:
            self.r = val / 2.0
        elif key == "start":
            self.a1 = val
        elif key == "end":
            self.a2 = val
        self._show()
        if self.live:
            self.set_live([self._build()])

    def on_button(self, key):
        if key == "flip":
            self.a1, self.a2 = self.a2, self.a1
            self._show()
            if self.live:
                self.set_live([self._build()])
            return
        super().on_button(key)


# ------------------------------------------------------------ arc endpoints
class ArcEndpointsTool(Tool):
    title = "Arc Endpoints"

    def setup(self):
        self.pts = []
        self.ends = None
        self.r = 1.0

    def ribbon(self):
        return [
            ("number", "radius", "Radius", self.r, False, "Radius (keeps the endpoints)"),
            ("number", "diameter", "Diameter", self.r * 2, False, "Diameter (keeps the endpoints)"),
        ]

    def prompt(self):
        return ["Enter the first endpoint", "Enter the second endpoint",
                "Pick a point the arc passes through"][len(self.pts)]

    def from_point(self):
        return self.pts[0] if self.pts else None

    def reset(self):
        self.pts = []

    def on_move(self, p, snap):
        if p is None or not self.pts:
            return
        if len(self.pts) == 1:
            self.preview([geom.line(self.pts[0], p)] if (p - self.pts[0]).Length > 1e-9 else [])
        else:
            try:
                self.preview([geom.arc3(self.pts[0], p, self.pts[1])])
            except Exception:
                pass

    def on_point(self, p, snap):
        if len(self.pts) < 2:
            if not self.pts:
                self.commit()
            self.pts.append(p)
            return
        try:
            arc = geom.arc3(self.pts[0], p, self.pts[1])
        except Exception:
            self.s.message("The three points are in line")
            return
        self.ends = tuple(self.pts)
        self.set_live([arc])
        self.r = arc.Curve.Radius
        self.set_field("radius", self.r)
        self.set_field("diameter", 2 * self.r)
        self.pts = []
        self.clear_preview()

    def on_field(self, key, val):
        r = val if key == "radius" else val / 2.0
        if not self.live or r <= 0:
            return
        arc = geom.arc_ends_radius(self.ends[0], self.ends[1], r, self.live[0].Shape.Edges[0])
        self.r = r
        self.set_live([arc])
        self.set_field("radius", r)
        self.set_field("diameter", 2 * r)


# ---------------------------------------------------------------- arc 3 pts
class Arc3PointsTool(Tool):
    title = "Arc 3 Points"

    def setup(self):
        self.pts = []
        self.done_pts = None

    def ribbon(self):
        return [("button", "edit1", "Edit P1", "Pick a new first point"),
                ("button", "edit2", "Edit P2", "Pick a new middle point"),
                ("button", "edit3", "Edit P3", "Pick a new last point")]

    def prompt(self):
        if self.editing:
            return "Pick the new point"
        return ["Enter the first point", "Enter the second point", "Enter the third point"][len(self.pts)]

    def reset(self):
        self.pts = []

    def on_move(self, p, snap):
        if p is None or not self.pts or self.editing:
            return
        if len(self.pts) == 1:
            if (p - self.pts[0]).Length > 1e-9:
                self.preview([geom.line(self.pts[0], p)])
        else:
            try:
                self.preview([geom.arc3(self.pts[0], self.pts[1], p)])
            except Exception:
                pass

    def on_point(self, p, snap):
        if self.editing and self.live:
            i = int(self.editing[-1]) - 1
            pts = list(self.done_pts)
            pts[i] = p
            self.editing = None
            try:
                self.set_live([geom.arc3(*pts)])
                self.done_pts = pts
            except Exception:
                self.s.message("The three points are in line")
            return
        if not self.pts:
            self.commit()
        self.pts.append(p)
        if len(self.pts) == 3:
            try:
                self.set_live([geom.arc3(*self.pts)])
                self.done_pts = list(self.pts)
            except Exception:
                self.s.message("The three points are in line")
            self.pts = []
            self.clear_preview()


# --------------------------------------------------------------- rectangle
class RectangleTool(Tool):
    title = "Rectangle"

    def setup(self):
        self.p1 = None
        self.anchor = None
        self.w, self.h = 1.0, 1.0
        self.center = False
        self.rot = 0.0
        self.radius = 0.0

    def ribbon(self):
        return [
            ("button", "edit1", "Edit Corner 1", "Pick a new first corner"),
            ("button", "edit2", "Edit Corner 2", "Pick a new opposite corner"),
            ("number", "w", "Width", self.w, True, "Width along Cplane X (lock both to place by base point)"),
            ("number", "h", "Height", self.h, True, "Height along Cplane Y"),
            ("toggle", "center", "Center Anchor", False, "First point is the center of the rectangle"),
            ("number", "radius", "Corner R", self.radius, False, "Corner fillet radius"),
            ("number", "rot", "Rotation", self.rot, False, "Rotation angle, CCW"),
        ]

    def prompt(self):
        if self.editing:
            return "Pick the new corner"
        if self.p1 is None:
            if self.locks.get("w") and self.locks.get("h"):
                return "Pick the base point (anchor)"
            return "Pick the center point" if self.center else "Pick the first corner"
        return "Pick the opposite corner"

    def reset(self):
        self.p1 = None

    def from_point(self):
        return self.p1

    def _dims(self, a, p):
        d = self.cp.flatten(p, a) - a
        a_ = math.radians(self.rot)
        du = self.cp.u * math.cos(a_) + self.cp.v * math.sin(a_)
        dv = self.cp.n.cross(du)
        w, h = d.dot(du), d.dot(dv)
        if self.center:
            w, h = 2 * abs(w), 2 * abs(h)
        if self.locks.get("w"):
            w = math.copysign(self.w, w) if not self.center else self.w
        if self.locks.get("h"):
            h = math.copysign(self.h, h) if not self.center else self.h
        return w, h

    def _build(self, a, w, h):
        r = min(self.radius, abs(w) / 2 - 1e-6, abs(h) / 2 - 1e-6)
        return geom.rectangle(a, w, h, self.cp, self.center, self.rot, max(r, 0.0))

    def on_move(self, p, snap):
        if self.p1 is None or p is None or self.editing:
            return
        w, h = self._dims(self.p1, p)
        if abs(w) > 1e-9 and abs(h) > 1e-9:
            self.preview(self._build(self.p1, w, h))
            if not self.locks.get("w"):
                self.set_field("w", abs(w))
            if not self.locks.get("h"):
                self.set_field("h", abs(h))

    def _make(self, a, w, h):
        self.anchor, self.w, self.h = a, w, h
        self.set_live(self._build(a, w, h))
        self.set_field("w", abs(w))
        self.set_field("h", abs(h))

    def on_point(self, p, snap):
        if self.editing and self.live:
            ed = self.editing
            self.editing = None
            if ed == "edit1":
                # keep the opposite corner
                if self.center:
                    self.anchor = p
                else:
                    opp = self.anchor + self._uv(self.w, self.h)
                    self.anchor = p
                    self.w, self.h = self._dims(p, opp)
            else:
                self.w, self.h = self._dims(self.anchor, p)
            self._make(self.anchor, self.w, self.h)
            return
        if self.p1 is None:
            self.commit()
            if self.locks.get("w") and self.locks.get("h"):
                self._make(p, self.w, self.h)
                return
            self.p1 = p
            return
        w, h = self._dims(self.p1, p)
        if abs(w) < 1e-9 or abs(h) < 1e-9:
            return
        self._make(self.p1, w, h)
        self.p1 = None
        self.clear_preview()

    def _uv(self, w, h):
        a_ = math.radians(self.rot)
        du = self.cp.u * math.cos(a_) + self.cp.v * math.sin(a_)
        dv = self.cp.n.cross(du)
        return du * w + dv * h

    def on_field(self, key, val):
        if key == "center":
            self.center = val
            return
        if key == "w":
            self.w = math.copysign(val, self.w) if self.w else val
        elif key == "h":
            self.h = math.copysign(val, self.h) if self.h else val
        elif key == "radius":
            self.radius = max(val, 0.0)
        elif key == "rot":
            self.rot = val
        if self.live and self.anchor is not None:
            self._make(self.anchor, self.w, self.h)


# ----------------------------------------------------------------- polygon
class PolygonTool(Tool):
    title = "Polygon"

    def setup(self):
        self.c = None
        self.center = None
        self.sides = 6
        self.r = 1.0
        self.corner = True
        self.rot = 0.0

    def ribbon(self):
        return [
            ("button", "editc", "Edit Center", "Pick a new center"),
            ("int", "sides", "Sides", self.sides, "Number of sides"),
            ("number", "radius", "Radius", self.r, True, "Radius"),
            ("number", "f2f", "Flat to Flat", self.f2f(), True,
             "Distance across the flats (even number of sides only)"),
            ("toggle", "corner", "To Corner", True,
             "Checked: radius to the corners (inscribed). Unchecked: radius to the flats (circumscribed)"),
            ("number", "rot", "Rotation", self.rot, False, "Rotation, CCW"),
        ]

    def prompt(self):
        self._update_f2f_state()
        if self.editing:
            return "Pick the new center"
        return "Pick the radius point" if self.center is not None else "Pick the center point"

    def reset(self):
        self.center = None

    # flat to flat only exists with parallel flats: an even number of sides
    def has_flats(self):
        return self.sides % 2 == 0

    def apothem(self):
        return self.r * math.cos(math.pi / self.sides) if self.corner else self.r

    def f2f(self):
        return 2 * self.apothem()

    def _update_f2f_state(self):
        on = self.has_flats()
        self.s.ribbon.set_enabled("f2f", on)
        if not on and self.locks.get("f2f"):
            self.s.ribbon.set_lock("f2f", False)

    def _size_locked(self):
        return self.locks.get("radius") or (self.locks.get("f2f") and self.has_flats())

    def _show_size(self):
        self.set_field("radius", self.r)
        if self.has_flats():
            self.set_field("f2f", self.f2f())

    def _build(self, c):
        return geom.polygon(c, self.r, self.sides, self.cp, self.corner, self.rot)

    def on_move(self, p, snap):
        if self.center is None or p is None or self._size_locked():
            return
        r = (self.cp.flatten(p, self.center) - self.center).Length
        if r > 1e-9:
            self.r = r
            self._show_size()
            self.preview(self._build(self.center))

    def on_point(self, p, snap):
        if self.editing == "editc" and self.live:
            self.c = p
            self.editing = None
            self.set_live(self._build(p))
            return
        if self.center is None:
            self.commit()
            if self._size_locked():
                self.c = p
                self.set_live(self._build(p))
                return
            self.center = p
            return
        r = (self.cp.flatten(p, self.center) - self.center).Length
        if r < 1e-9:
            return
        self.r = r
        self.c = self.center
        self.set_live(self._build(self.c))
        self.center = None
        self.clear_preview()

    def on_field(self, key, val):
        if key == "sides":
            self.sides = max(3, int(val))
            self.set_field("sides", self.sides)
            self._update_f2f_state()
        elif key == "radius" and val > 0:
            self.r = val
        elif key == "f2f" and val > 0:
            if not self.has_flats():
                return
            a = val / 2.0
            self.r = a / math.cos(math.pi / self.sides) if self.corner else a
        elif key == "corner":
            self.corner = val
        elif key == "rot":
            self.rot = val
        self._show_size()
        if self.live and self.c is not None:
            self.set_live(self._build(self.c))
        elif self.center is not None and key in ("radius", "f2f"):
            # size typed after the center: create it right away
            self.c, self.center = self.center, None
            self.clear_preview()
            self.set_live(self._build(self.c))

"""AutoCursor: snapping the cursor to points on existing geometry."""

import math

import FreeCAD as App

from . import entities, geom

V = App.Vector

SNAP_TYPES = ["Origin", "Point", "End", "Mid", "Center", "Quad",
              "Intersection", "Tangent", "Perpendicular", "Horiz/Vert", "Nearest"]
LABELS = {"Origin": "Org", "Point": "Pt", "End": "End", "Mid": "Mid", "Center": "Ctr",
          "Quad": "Quad", "Intersection": "Int", "Tangent": "Tan",
          "Perpendicular": "Perp", "Horiz": "H", "Vert": "V", "Nearest": "Near",
          "Typed": "", "Cursor": ""}
PRIORITY = {"Origin": 0, "Point": 0, "End": 0, "Center": 0, "Intersection": 0,
            "Mid": 1, "Quad": 1, "Tangent": 2, "Perpendicular": 2, "Nearest": 5}


class Snap:
    def __init__(self, point, kind="Cursor", obj=None, sub=None, hit=None, pos=None):
        self.point = point          # resulting (snapped) point
        self.kind = kind
        self.obj = obj              # entity under the cursor, if any
        self.sub = sub              # its sub-element name ("Edge1")
        self.hit = hit              # raw point under the cursor on that entity
        self.pos = pos              # screen position

    @property
    def edge(self):
        if self.obj is None:
            return None
        try:
            if self.sub and self.sub.startswith("Edge"):
                return self.obj.Shape.getElement(self.sub)
            if self.obj.Shape.Edges:
                return self.obj.Shape.Edges[0]
        except Exception:
            pass
        return None

    @property
    def is_geometry(self):
        return self.kind not in ("Cursor", "Horiz", "Vert")


class Snapper:
    def __init__(self):
        self.enabled = {t: True for t in SNAP_TYPES}
        self.enabled["Nearest"] = False
        self.only = None            # Mastercam "Only" filter: one snap type
        self.radius_px = 10
        self._cache = {}

    def active(self, kind):
        if self.only:
            return kind == self.only
        return self.enabled.get(kind, False)

    # ------------------------------------------------------------ picking ray
    @staticmethod
    def ray(view, pos):
        p0 = view.getPoint(*pos)
        if view.getCameraType() == "Perspective":
            cam = view.getCameraNode().position.getValue()
            d = p0 - V(cam[0], cam[1], cam[2])
            if d.Length > 1e-12:
                return p0, d.normalize()
        return p0, V(view.getViewDirection()).normalize()

    @staticmethod
    def pixel_size(view, pos):
        a = view.getPoint(pos[0], pos[1])
        b = view.getPoint(pos[0] + 10, pos[1])
        return max((b - a).Length / 10.0, 1e-9)

    def _keypoints(self, obj):
        try:
            shape = obj.Shape
            key = (shape.hashCode(), str(obj.Placement))
        except Exception:
            return [], []
        c = self._cache.get(obj.Name)
        if c and c[0] == key:
            return c[1], c[2]
        pts = []
        edges = list(shape.Edges)
        if not edges:
            pts = [(v.Point, "Point") for v in shape.Vertexes]
        for e in edges:
            pts += geom.keypoints(e)
        self._cache[obj.Name] = (key, pts, edges)
        return pts, edges

    # ---------------------------------------------------------------- snap
    def snap(self, view, pos, cplane, from_pt=None, exclude=()):
        p0, d = self.ray(view, pos)
        tol = self.radius_px * self.pixel_size(view, pos)
        exclude_names = {o.Name for o in exclude if entities.alive(o)}

        def ray_dist(q):
            w = q - p0
            return (w - d * w.dot(d)).Length

        # what is under the cursor
        hover_obj = hover_sub = hover_pt = None
        try:
            info = view.getObjectInfo(pos)
        except Exception:
            info = None
        if info:
            o = App.getDocument(info["Document"]).getObject(info["Object"])
            if o is not None and o.Name not in exclude_names and o.isDerivedFrom("Part::Feature"):
                hover_obj, hover_sub = o, info.get("Component", "")
                hover_pt = V(info["x"], info["y"], info["z"])
        cursor = cplane.intersect_ray(p0, d)
        if from_pt is not None:
            # free picks stay in the plane of the first point
            cursor = cplane.intersect_ray(p0, d, through=from_pt)

        cands = []
        if self.active("Origin"):
            cands.append((V(0, 0, 0), "Origin"))
        objs = [o for o in entities.geometry_objects() if o.Name not in exclude_names]
        hover_edge = None
        for o in objs:
            pts, edges = self._keypoints(o)
            for p, k in pts:
                if self.active(k):
                    cands.append((p, k))
            if o is hover_obj and edges:
                try:
                    hover_edge = o.Shape.getElement(hover_sub) if hover_sub.startswith("Edge") else edges[0]
                except Exception:
                    hover_edge = edges[0]

        if hover_edge is not None:
            if self.active("Intersection"):
                for o in objs:
                    if o is hover_obj:
                        continue
                    _, edges = self._keypoints(o)
                    for e in edges:
                        bb = e.BoundBox
                        bb.enlarge(tol * 2)
                        if not bb.isInside(hover_pt):
                            continue
                        for p in geom.intersections(hover_edge, e):
                            cands.append((p, "Intersection"))
            if from_pt is not None:
                if self.active("Tangent"):
                    for p in geom.tangent_points_from(from_pt, hover_edge):
                        cands.append((p, "Tangent"))
                if self.active("Perpendicular"):
                    p = geom.perpendicular_foot(from_pt, hover_edge)
                    if p is not None:
                        cands.append((p, "Perpendicular"))
            if self.active("Nearest"):
                cands.append((hover_pt, "Nearest"))

        best = None
        for p, k in cands:
            dd = ray_dist(p)
            if dd > tol:
                continue
            score = (PRIORITY.get(k, 3), dd)
            if best is None or score < best[0]:
                best = (score, p, k)
        if best is not None:
            return Snap(V(best[1]), best[2], hover_obj, hover_sub, hover_pt, pos)

        if from_pt is not None and self.active("Horiz/Vert"):
            w = cursor - from_pt
            du, dv = w.dot(cplane.u), w.dot(cplane.v)
            if abs(dv) < tol and abs(du) > tol:
                return Snap(from_pt + cplane.u * du, "Horiz", hover_obj, hover_sub, hover_pt, pos)
            if abs(du) < tol and abs(dv) > tol:
                return Snap(from_pt + cplane.v * dv, "Vert", hover_obj, hover_sub, hover_pt, pos)
        return Snap(cursor, "Cursor", hover_obj, hover_sub, hover_pt, pos)

"""Edit commands: fillet, chamfer, trim/break, close arc, delete duplicates."""

import FreeCAD as App
import FreeCADGui as Gui
import Part

from . import entities, geom
from .tools_base import PickTool


def _two_picks_prompt(first):
    return "Select the second entity" if first else "Select the first entity"


class FilletTool(PickTool):
    title = "Fillet"

    def setup(self):
        self.first = None
        self.r = 1.0
        self.trim = True

    def ribbon(self):
        return [("number", "radius", "Radius", self.r, False, "Fillet radius"),
                ("toggle", "trim", "Trim", True, "Trim the entities to the fillet")]

    def prompt(self):
        return _two_picks_prompt(self.first) + " (pick on the side to keep)"

    def reset(self):
        self.first = None

    def on_field(self, key, val):
        if key == "radius" and val > 0:
            self.r = val
        elif key == "trim":
            self.trim = val

    def on_point(self, p, snap):
        e = self.picked_edge(snap)
        if e is None:
            return
        pick = (snap.obj, e, snap.hit or p)
        if self.first is None:
            self.first = pick
            return
        (o1, e1, h1), (o2, e2, h2) = self.first, pick
        self.first = None
        if o1 is o2:
            self.s.message("Select two different entities")
            return
        if geom.is_line(e1) and geom.is_line(e2):
            arc, n1, n2 = geom.fillet_lines(e1, h1, e2, h2, self.r)
        else:
            arc, n1, n2 = geom.fillet_general(e1, h1, e2, h2, self.r)

        def run():
            entities.make(arc)
            if self.trim:
                if n1 is not None:
                    entities.replace_edge(o1, [n1])
                if n2 is not None:
                    entities.replace_edge(o2, [n2])
        self.modify("Fillet", run)


class ChamferTool(PickTool):
    title = "Chamfer"
    METHODS = ["Distance", "2 Distances", "Distance/Angle", "Width"]

    def setup(self):
        self.first = None
        self.method = "Distance"
        self.d1, self.d2, self.ang, self.width = 1.0, 1.0, 45.0, 1.0
        self.trim = True

    def ribbon(self):
        return [("choice", "method", "Method", self.METHODS, self.method, "How the chamfer is sized"),
                ("number", "d1", "Distance 1", self.d1, False, "Distance along the first line"),
                ("number", "d2", "Distance 2", self.d2, False, "Distance along the second line (2 Distances)"),
                ("number", "ang", "Angle", self.ang, False, "Angle from the first line (Distance/Angle)"),
                ("number", "width", "Width", self.width, False, "Length of the chamfer line (Width)"),
                ("toggle", "trim", "Trim", True, "Trim the lines to the chamfer")]

    def prompt(self):
        return _two_picks_prompt(self.first) + " line (pick on the side to keep)"

    def reset(self):
        self.first = None

    def on_field(self, key, val):
        setattr(self, key, val)

    def on_point(self, p, snap):
        e = self.picked_edge(snap)
        if e is None:
            return
        if not geom.is_line(e):
            self.s.message("Chamfer works on lines")
            return
        pick = (snap.obj, e, snap.hit or p)
        if self.first is None:
            self.first = pick
            return
        (o1, e1, h1), (o2, e2, h2) = self.first, pick
        self.first = None
        if o1 is o2:
            self.s.message("Select two different lines")
            return
        ch, n1, n2 = geom.chamfer_lines(e1, h1, e2, h2, self.method, self.d1, self.d2, self.ang, self.width)

        def run():
            entities.make(ch)
            if self.trim:
                if n1 is not None:
                    entities.replace_edge(o1, [n1])
                if n2 is not None:
                    entities.replace_edge(o2, [n2])
        self.modify("Chamfer", run)


class TrimTool(PickTool):
    title = "Trim/Break/Extend"
    MODES = ["1 Entity", "2 Entities", "3 Entities", "Divide", "To Point"]

    def setup(self):
        self.mode = "1 Entity"
        self.picks = []

    def ribbon(self):
        return [("choice", "mode", "Mode", self.MODES, self.mode,
                 "1 Entity: entity to trim (side to keep), then the boundary\n"
                 "2 Entities: both entities (sides to keep)\n"
                 "3 Entities: two outside entities, then the middle one (side to keep)\n"
                 "Divide: pick the piece to remove\n"
                 "To Point: entity (side to keep), then the point to trim/extend to")]

    def prompt(self):
        n = len(self.picks)
        m = self.mode
        if m == "1 Entity":
            return "Select the entity to trim (side to keep)" if n == 0 else "Select the entity to trim to"
        if m == "2 Entities":
            return "Select the first entity (side to keep)" if n == 0 else "Select the second entity (side to keep)"
        if m == "3 Entities":
            return ["Select the first outside entity", "Select the second outside entity",
                    "Select the entity to trim (side to keep)"][n]
        if m == "Divide":
            return "Select the piece to remove"
        return "Select the entity to trim/extend (side to keep)" if n == 0 else "Pick the point to trim to"

    def reset(self):
        self.picks = []

    def on_field(self, key, val):
        if key == "mode":
            self.mode = val
            self.picks = []

    def _best_x(self, e1, e2, near):
        pts = geom.intersections(e1, e2, True, True)
        if not pts:
            raise ValueError("The entities do not intersect")
        return geom.nearest(pts, near)

    def on_point(self, p, snap):
        if self.mode == "To Point" and len(self.picks) == 1:
            o, e, h = self.picks[0]
            self.picks = []
            x = geom.trim_curve_point(e, p)
            new = geom.trim_to_point(e, h, x)
            if new is None:
                raise ValueError("Cannot trim this entity to that point")
            self.modify("Trim", lambda: entities.replace_edge(o, [new]))
            return
        e = self.picked_edge(snap)
        if e is None:
            return
        self.picks.append((snap.obj, e, snap.hit or p))
        m = self.mode
        if m == "Divide":
            o, e, h = self.picks.pop()
            others = []
            for ob in entities.geometry_objects():
                if ob is not o:
                    others += ob.Shape.Edges
            pieces = geom.divide(e, h, others)
            if pieces is None:
                raise ValueError("A circle needs two intersections to divide")
            self.modify("Divide", lambda: entities.replace_edge(o, pieces))
        elif m == "1 Entity" and len(self.picks) == 2:
            (o1, e1, h1), (o2, e2, h2) = self.picks
            self.picks = []
            x = self._best_x(e1, e2, h2)
            new = geom.trim_to_point(e1, h1, x)
            if new is None:
                raise ValueError("Cannot trim this entity")
            self.modify("Trim", lambda: entities.replace_edge(o1, [new]))
        elif m == "2 Entities" and len(self.picks) == 2:
            (o1, e1, h1), (o2, e2, h2) = self.picks
            self.picks = []
            x = self._best_x(e1, e2, (h1 + h2) * 0.5)
            n1 = geom.trim_to_point(e1, h1, x)
            n2 = geom.trim_to_point(e2, h2, x)
            if n1 is None or n2 is None:
                raise ValueError("Cannot trim these entities")

            def run():
                entities.replace_edge(o1, [n1])
                entities.replace_edge(o2, [n2])
            self.modify("Trim", run)
        elif m == "3 Entities" and len(self.picks) == 3:
            (o1, e1, h1), (o2, e2, h2), (o3, e3, h3) = self.picks
            self.picks = []
            x1 = self._best_x(e3, e1, h1)
            x2 = self._best_x(e3, e2, h2)
            n1 = geom.trim_to_point(e1, h1, x1)
            n2 = geom.trim_to_point(e2, h2, x2)
            mid = self._between(e3, h3, x1, x2)

            def run():
                if n1 is not None:
                    entities.replace_edge(o1, [n1])
                if n2 is not None:
                    entities.replace_edge(o2, [n2])
                entities.replace_edge(o3, [mid])
            self.modify("Trim", run)
        elif m == "To Point":
            self.s.message("Pick the point to trim to")

    @staticmethod
    def _between(e, keep, x1, x2):
        if geom.is_line(e):
            return geom.line(x1, x2)
        c = e.Curve
        t1, t2 = c.parameter(x1), c.parameter(x2)
        tk = c.parameter(keep)
        import math
        two = 2 * math.pi
        # arc from t1 to t2 CCW contains tk?
        span = (t2 - t1) % two
        if (tk - t1) % two <= span:
            return Part.ArcOfCircle(c, t1, t1 + span).toShape()
        return Part.ArcOfCircle(c, t2, t2 + (two - span)).toShape()


class CloseArcTool(PickTool):
    title = "Close Arc"

    def prompt(self):
        return "Select an arc to make it a full circle"

    def on_point(self, p, snap):
        e = self.picked_edge(snap)
        if e is None:
            return
        if not geom.is_circle(e) or e.isClosed():
            self.s.message("Select an arc")
            return
        o = snap.obj
        self.modify("Close Arc", lambda: entities.replace_edge(o, [Part.Edge(e.Curve)]))


def delete_duplicates():
    doc = App.ActiveDocument
    if doc is None:
        return 0
    sel = [o for o in Gui.Selection.getSelection() if o.isDerivedFrom("Part::Feature")]
    objs = sel or entities.geometry_objects(doc)
    seen = {}
    dup = []
    for o in objs:
        try:
            sig = (entities.kind_for(o.Shape), geom.signature(o.Shape))
        except Exception:
            continue
        if sig in seen:
            dup.append(o)
        else:
            seen[sig] = o
    if dup:
        doc.openTransaction("Delete Duplicates")
        for o in dup:
            doc.removeObject(o.Name)
        doc.commitTransaction()
        doc.recompute()
    App.Console.PrintMessage("DirectGeo: removed %d duplicate entities\n" % len(dup))
    return len(dup)

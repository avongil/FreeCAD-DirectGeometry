"""Editable geometry properties on entities, FreeCAD style.

Each entity stays a plain Part::Feature (files open without this workbench),
with extra properties in a "Geometry" group of the Data tab: Center, Radius,
Diameter, Start/End angle, Start/End point, Length... Editing one rebuilds the
shape directly (no history). Moving the entity (Placement, Dynamic Transform,
trim...) refreshes the values. Display properties (Line Color, Line Width,
Point Size...) are FreeCAD's own, in the View tab.
"""

import math

import FreeCAD as App
import Part

V = App.Vector
GROUP = "Geometry"

# kind: [(name, type, tooltip)]
SPECS = {
    "Point": [
        ("Position", "App::PropertyVectorDistance", "Point location X, Y, Z (global)"),
    ],
    "Line": [
        ("StartPoint", "App::PropertyVectorDistance", "First endpoint X, Y, Z (global)"),
        ("EndPoint", "App::PropertyVectorDistance", "Second endpoint X, Y, Z (global)"),
        ("Length", "App::PropertyLength", "Length; changing it keeps the start point"),
        ("Angle", "App::PropertyAngle", "Angle in the XY plane, CCW from X; changing it keeps the start point"),
    ],
    "Circle": [
        ("Center", "App::PropertyVectorDistance", "Center X, Y, Z (global)"),
        ("Radius", "App::PropertyLength", "Radius"),
        ("Diameter", "App::PropertyLength", "Diameter"),
        ("Normal", "App::PropertyVector", "Normal of the circle plane"),
    ],
    "Arc": [
        ("Center", "App::PropertyVectorDistance", "Center X, Y, Z (global)"),
        ("Radius", "App::PropertyLength", "Radius"),
        ("Diameter", "App::PropertyLength", "Diameter"),
        ("StartAngle", "App::PropertyAngle", "Start angle, CCW about the normal"),
        ("EndAngle", "App::PropertyAngle", "End angle, CCW about the normal"),
        ("Normal", "App::PropertyVector", "Normal of the arc plane"),
        ("StartPoint", "App::PropertyVectorDistance", "Start point (read only)"),
        ("EndPoint", "App::PropertyVectorDistance", "End point (read only)"),
    ],
}
READ_ONLY = {"Arc": ("StartPoint", "EndPoint")}
TOL = 1e-9

_busy = set()


def _kind(obj):
    return getattr(obj, "DGKind", None)


def _edge(obj):
    sh = obj.Shape
    return sh.Edges[0] if sh.Edges else None


def ensure(obj):
    """Add the geometry properties for this entity's kind and fill them."""
    kind = _kind(obj)
    if kind not in SPECS:
        return
    _busy.add(obj.Name)
    try:
        for name, typ, tip in SPECS[kind]:
            if name not in obj.PropertiesList:
                obj.addProperty(typ, name, GROUP, tip)
        for name in READ_ONLY.get(kind, ()):
            obj.setEditorMode(name, 1)
    finally:
        _busy.discard(obj.Name)
    sync(obj)


def retype(obj, kind):
    """Switch an entity to another kind (arc <-> circle after trim/close)."""
    keep = {n for n, _, _ in SPECS.get(kind, [])}
    _busy.add(obj.Name)
    try:
        for name, _, _ in SPECS.get(_kind(obj), []):
            if name not in keep and name in obj.PropertiesList:
                obj.removeProperty(name)
        obj.DGKind = kind
    finally:
        _busy.discard(obj.Name)
    ensure(obj)


def ensure_document(doc):
    for o in doc.Objects:
        if _kind(o) in SPECS:
            ensure(o)


def _set(obj, name, value):
    try:
        cur = getattr(obj, name)
        cur = cur.Value if hasattr(cur, "Value") else cur
        if isinstance(value, V):
            if (V(cur) - value).Length < TOL:
                return
        elif abs(float(cur) - float(value)) < TOL:
            return
    except Exception:
        pass
    setattr(obj, name, value)


def _deg(rad):
    return math.degrees(rad)


def sync(obj):
    """Shape -> properties."""
    kind = _kind(obj)
    if kind not in SPECS or obj.Name in _busy:
        return
    _busy.add(obj.Name)
    try:
        sh = obj.Shape
        if kind == "Point":
            if sh.Vertexes:
                _set(obj, "Position", sh.Vertexes[0].Point)
            return
        e = _edge(obj)
        if e is None:
            return
        if kind == "Line":
            a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
            _set(obj, "StartPoint", a)
            _set(obj, "EndPoint", b)
            _set(obj, "Length", (b - a).Length)
            _set(obj, "Angle", _deg(math.atan2(b.y - a.y, b.x - a.x)))
        else:
            c = e.Curve
            _set(obj, "Center", c.Center)
            _set(obj, "Radius", c.Radius)
            _set(obj, "Diameter", 2 * c.Radius)
            _set(obj, "Normal", c.Axis)
            if kind == "Arc":
                _set(obj, "StartAngle", _deg(e.FirstParameter))
                _set(obj, "EndAngle", _deg(e.LastParameter))
                _set(obj, "StartPoint", e.Vertexes[0].Point)
                _set(obj, "EndPoint", e.Vertexes[-1].Point)
    except Exception as ex:
        App.Console.PrintWarning("DirectGeo: %s: %s\n" % (obj.Name, ex))
    finally:
        _busy.discard(obj.Name)


def _val(obj, name):
    v = getattr(obj, name)
    return v.Value if hasattr(v, "Value") else v


def rebuild(obj, prop):
    """Edited property -> new shape."""
    kind = _kind(obj)
    if kind == "Point":
        return Part.Vertex(V(obj.Position))
    e = _edge(obj)
    if kind == "Line":
        a, b = V(obj.StartPoint), V(obj.EndPoint)
        if prop in ("Length", "Angle"):
            d = e.Vertexes[-1].Point - e.Vertexes[0].Point
            a = e.Vertexes[0].Point
            L = _val(obj, "Length") if prop == "Length" else d.Length
            if prop == "Angle":
                ang = math.radians(_val(obj, "Angle"))
                h = math.hypot(d.x, d.y)
                if h < TOL:
                    h = L
                d = V(h * math.cos(ang), h * math.sin(ang), d.z)
            if L < TOL or d.Length < TOL:
                raise ValueError("Length must be greater than zero")
            b = a + V(d).normalize() * L
        if (b - a).Length < TOL:
            raise ValueError("The endpoints coincide")
        return Part.LineSegment(a, b).toShape()
    c = e.Curve
    r = _val(obj, "Diameter") / 2 if prop == "Diameter" else _val(obj, "Radius")
    if r < TOL:
        raise ValueError("Radius must be greater than zero")
    n = V(obj.Normal)
    if n.Length < TOL:
        raise ValueError("Normal must not be zero")
    n.normalize()
    circ = Part.Circle(V(obj.Center), n, r)
    xa = V(c.XAxis)
    xa = xa - n * xa.dot(n)
    if xa.Length > TOL:
        circ.XAxis = xa.normalize()
    if kind == "Circle":
        return Part.Edge(circ)
    a1 = math.radians(_val(obj, "StartAngle"))
    a2 = math.radians(_val(obj, "EndAngle"))
    while a2 <= a1 + TOL:
        a2 += 2 * math.pi
    return Part.ArcOfCircle(circ, a1, a2).toShape()


GEOMETRY_PROPS = {name for spec in SPECS.values() for name, _, _ in spec}


class _Observer:
    def slotChangedObject(self, obj, prop):
        try:
            if obj.Name in _busy or _kind(obj) not in SPECS:
                return
            doc = obj.Document
            if getattr(doc, "Transacting", False) or "Restore" in obj.State:
                return
        except Exception:
            return
        if prop in ("Shape", "Placement"):
            if any(n not in obj.PropertiesList for n, _, _ in SPECS[_kind(obj)]):
                ensure(obj)
            else:
                sync(obj)
        elif prop in GEOMETRY_PROPS:
            if prop in READ_ONLY.get(_kind(obj), ()):
                return
            _busy.add(obj.Name)
            try:
                sh = rebuild(obj, prop)
                obj.Placement = App.Placement()
                obj.Shape = sh
            except Exception as ex:
                App.Console.PrintError("DirectGeo: %s\n" % ex)
            finally:
                _busy.discard(obj.Name)
            sync(obj)

    def slotFinishRestoreDocument(self, doc):
        # files saved before these properties existed get them on load
        try:
            ensure_document(doc)
        except Exception:
            pass


_observer = None


def install():
    global _observer
    if _observer is None:
        _observer = _Observer()
        App.addDocumentObserver(_observer)
        for doc in App.listDocuments().values():
            ensure_document(doc)

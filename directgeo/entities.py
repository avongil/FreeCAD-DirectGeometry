"""Document entities: plain Part::Feature objects (no history)."""

import FreeCAD as App

from . import props

LIVE = (0.35, 0.85, 1.0)     # light blue: live entity, still editable
DONE = (0.0, 0.62, 0.0)      # green: committed geometry
POINT_SIZE = 6.0
LINE_WIDTH = 2.0


def alive(obj):
    try:
        return obj is not None and obj.Document is not None and obj.Name is not None
    except Exception:
        return False


def kind_for(shape):
    if not shape.Edges:
        return "Point"
    e = shape.Edges[0]
    name = type(e.Curve).__name__
    if name == "Line":
        return "Line"
    if name == "Circle":
        return "Circle" if e.isClosed() else "Arc"
    return "Curve"


def make(shape, live=False, doc=None):
    doc = doc or App.ActiveDocument
    kind = kind_for(shape)
    obj = doc.addObject("Part::Feature", kind)
    obj.addProperty("App::PropertyString", "DGKind", "DirectGeo",
                    "Entity type created by the Direct Geometry workbench")
    obj.setEditorMode("DGKind", 1)
    obj.DGKind = kind
    obj.Shape = shape
    props.ensure(obj)
    style(obj, LIVE if live else DONE)
    return obj


def set_shape(obj, shape):
    """Replace an entity's geometry; its kind (and properties) may change."""
    kind = kind_for(shape)
    if getattr(obj, "DGKind", None) not in (None, kind):
        props.retype(obj, kind)
    obj.Placement = App.Placement()
    obj.Shape = shape
    props.sync(obj)


def style(obj, color):
    vo = getattr(obj, "ViewObject", None)
    if vo is None:
        return
    for prop, val in (("LineColor", color), ("PointColor", color),
                      ("LineWidth", LINE_WIDTH), ("PointSize", POINT_SIZE)):
        try:
            setattr(vo, prop, val)
        except Exception:
            pass


LOOK_PROPS = ("LineColor", "PointColor", "LineWidth", "PointSize", "DrawStyle")


def get_look(obj):
    vo = getattr(obj, "ViewObject", None)
    if vo is None:
        return {}
    return {p: getattr(vo, p) for p in LOOK_PROPS if hasattr(vo, p)}


def set_look(obj, look):
    vo = getattr(obj, "ViewObject", None)
    if vo is None:
        return
    for p, v in (look or {}).items():
        try:
            setattr(vo, p, v)
        except Exception:
            pass


def geometry_objects(doc=None):
    """Visible Part features usable for snapping/picking."""
    doc = doc or App.ActiveDocument
    if doc is None:
        return []
    out = []
    for o in doc.Objects:
        if not o.isDerivedFrom("Part::Feature"):
            continue
        vo = getattr(o, "ViewObject", None)
        if vo is not None and not vo.Visibility:
            continue
        out.append(o)
    return out


def replace_edge(obj, new_shapes):
    """Replace an entity by one or more shapes (first reuses the object)."""
    doc = obj.Document
    if not new_shapes:
        doc.removeObject(obj.Name)
        return []
    set_shape(obj, new_shapes[0])
    out = [obj]
    look = get_look(obj)
    for sh in new_shapes[1:]:
        new = make(sh, doc=doc)
        set_look(new, look)
        out.append(new)
    return out

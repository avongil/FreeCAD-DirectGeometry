"""Coin3D preview helpers: rubber-band preview, snap marker, system axes."""

import FreeCADGui as Gui
from pivy import coin


def _marker(name, size):
    try:
        return Gui.getMarkerIndex(name, size)
    except Exception:
        return coin.SoMarkerSet.CIRCLE_FILLED_7_7


def _unpickable():
    ps = coin.SoPickStyle()
    ps.style = coin.SoPickStyle.UNPICKABLE
    return ps


def discretize(shapes, n=48):
    lines, points = [], []
    for sh in shapes:
        if sh is None:
            continue
        if not sh.Edges:
            points += [v.Point for v in sh.Vertexes]
            continue
        for e in sh.Edges:
            if type(e.Curve).__name__ == "Line":
                lines.append([e.Vertexes[0].Point, e.Vertexes[-1].Point])
            else:
                lines.append(e.discretize(n))
    return lines, points


class Tracker:
    """Polylines and points drawn into the active 3D view."""

    def __init__(self, color=(1.0, 1.0, 0.3), width=2.0, dashed=False, on_top=True):
        self.root = coin.SoAnnotation() if on_top else coin.SoSeparator()
        self.root.addChild(_unpickable())
        self.color = coin.SoBaseColor()
        self.color.rgb = color
        self.root.addChild(self.color)
        ds = coin.SoDrawStyle()
        ds.lineWidth = width
        ds.pointSize = 5
        if dashed:
            ds.linePattern = 0x0F0F
        self.root.addChild(ds)
        self.coords = coin.SoCoordinate3()
        self.root.addChild(self.coords)
        self.lineset = coin.SoLineSet()
        self.root.addChild(self.lineset)
        psep = coin.SoSeparator()
        self.pcoords = coin.SoCoordinate3()
        self.markers = coin.SoMarkerSet()
        self.markers.markerIndex = _marker("circle", 9)
        psep.addChild(self.pcoords)
        psep.addChild(self.markers)
        self.root.addChild(psep)
        self.sg = None

    def attach(self, view):
        if self.sg is None:
            self.sg = view.getSceneGraph()
            self.sg.addChild(self.root)

    def detach(self):
        if self.sg is not None:
            self.sg.removeChild(self.root)
            self.sg = None

    def set_polylines(self, lines, points=()):
        flat, counts = [], []
        for pl in lines:
            if len(pl) < 2:
                continue
            flat += [(p.x, p.y, p.z) for p in pl]
            counts.append(len(pl))
        self.coords.point.setNum(len(flat))
        if flat:
            self.coords.point.setValues(0, len(flat), flat)
        self.lineset.numVertices.setNum(len(counts))
        if counts:
            self.lineset.numVertices.setValues(0, len(counts), counts)
        pts = [(p.x, p.y, p.z) for p in points]
        self.pcoords.point.setNum(len(pts))
        if pts:
            self.pcoords.point.setValues(0, len(pts), pts)

    def set_shapes(self, shapes):
        lines, points = discretize(shapes)
        self.set_polylines(lines, points)

    def clear(self):
        self.set_polylines([], [])


class SnapMarker:
    """Marker + label shown at the AutoCursor position (End, Mid, Ctr...)."""

    def __init__(self):
        self.root = coin.SoAnnotation()
        self.root.addChild(_unpickable())
        self.switch = coin.SoSwitch()
        self.root.addChild(self.switch)
        g = coin.SoSeparator()
        self.switch.addChild(g)
        col = coin.SoBaseColor()
        col.rgb = (1.0, 0.55, 0.0)
        g.addChild(col)
        self.coords = coin.SoCoordinate3()
        g.addChild(self.coords)
        m = coin.SoMarkerSet()
        m.markerIndex = _marker("square", 9)
        g.addChild(m)
        self.trans = coin.SoTranslation()
        g.addChild(self.trans)
        font = coin.SoFont()
        font.size = 13
        g.addChild(font)
        self.text = coin.SoText2()
        g.addChild(self.text)
        self.sg = None
        self.switch.whichChild = -1

    def attach(self, view):
        if self.sg is None:
            self.sg = view.getSceneGraph()
            self.sg.addChild(self.root)

    def detach(self):
        if self.sg is not None:
            self.sg.removeChild(self.root)
            self.sg = None

    def show(self, p, label, offset):
        self.coords.point.setValues(0, 1, [(p.x, p.y, p.z)])
        self.coords.point.setNum(1)
        q = p + offset
        self.trans.translation = (q.x, q.y, q.z)
        self.text.string = label
        self.switch.whichChild = 0

    def hide(self):
        self.switch.whichChild = -1


class Axes:
    """System axes at the origin (F9)."""

    def __init__(self):
        self.root = coin.SoSeparator()
        self.root.addChild(_unpickable())
        self.sg = None
        self.length = 1.0
        self.coords = []

    def build(self, length):
        self.root.removeAllChildren()
        self.root.addChild(_unpickable())
        ds = coin.SoDrawStyle()
        ds.lineWidth = 1.5
        ds.linePattern = 0xF0F0
        self.root.addChild(ds)
        for axis, col, lab in (((1, 0, 0), (1, 0.2, 0.2), "X"),
                               ((0, 1, 0), (0.2, 0.9, 0.2), "Y"),
                               ((0, 0, 1), (0.3, 0.5, 1), "Z")):
            s = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb = col
            s.addChild(c)
            co = coin.SoCoordinate3()
            end = tuple(a * length for a in axis)
            co.point.setValues(0, 2, [(0, 0, 0), end])
            s.addChild(co)
            s.addChild(coin.SoLineSet())
            t = coin.SoTranslation()
            t.translation = end
            s.addChild(t)
            txt = coin.SoText2()
            txt.string = lab
            s.addChild(txt)
            self.root.addChild(s)

    def toggle(self, view, length):
        if self.sg is not None:
            self.sg.removeChild(self.root)
            self.sg = None
            return False
        self.build(length)
        self.sg = view.getSceneGraph()
        self.sg.addChild(self.root)
        return True

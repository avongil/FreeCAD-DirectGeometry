"""Pure geometry helpers (no GUI). Everything works in 3D; planar entities
take their plane from a CPlane-like object with u, v, n vectors."""

import math

import FreeCAD as App
import Part

V = App.Vector
TOL = 1e-7
BIG = 1e5   # half length used to "extend" lines for intersections


# ---------------------------------------------------------------- builders
def line(a, b):
    return Part.LineSegment(V(a), V(b)).toShape()


def circle_curve(center, r, cp):
    c = Part.Circle(V(center), V(cp.n), r)
    c.XAxis = V(cp.u)
    return c


def circle(center, r, cp):
    return Part.Edge(circle_curve(center, r, cp))


def arc_polar(center, r, a1, a2, cp):
    """CCW arc in the Cplane from angle a1 to a2 (degrees)."""
    a1 = math.radians(a1)
    a2 = math.radians(a2)
    while a2 <= a1 + TOL:
        a2 += 2 * math.pi
    return Part.ArcOfCircle(circle_curve(center, r, cp), a1, a2).toShape()


def arc3(p1, p2, p3):
    """Arc from p1 through p2 to p3 (any plane)."""
    return Part.Arc(V(p1), V(p2), V(p3)).toShape()


def arc_ends_radius(p1, p2, r, ref_arc):
    """Arc between p1 and p2 with radius r, keeping the side/size of ref_arc."""
    c0 = ref_arc.Curve.Center
    n = ref_arc.Curve.Axis
    chord = p2 - p1
    h = chord.Length / 2
    if r < h - TOL:
        raise ValueError("Radius smaller than half the chord")
    m = (p1 + p2) * 0.5
    w = n.cross(chord).normalize()
    k = math.sqrt(max(r * r - h * h, 0.0))
    mid0 = ref_arc.valueAt((ref_arc.FirstParameter + ref_arc.LastParameter) / 2)
    side_c = 1.0 if (c0 - m).dot(w) >= 0 else -1.0
    side_m = 1.0 if (mid0 - m).dot(w) >= 0 else -1.0
    cs = k * side_c
    mm = cs + r if side_m > 0 else cs - r
    return arc3(p1, m + w * mm, p2)


def rectangle(anchor, w, h, cp, center=False, rot=0.0, radius=0.0):
    """List of edges (4 lines + optional 4 corner arcs) in the Cplane."""
    a = math.radians(rot)
    du = cp.u * math.cos(a) + cp.v * math.sin(a)
    dv = cp.n.cross(du)
    if center:
        loc = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    else:
        loc = [(0, 0), (w, 0), (w, h), (0, h)]
    pts = [anchor + du * x + dv * y for x, y in loc]
    return _closed_poly(pts, radius)


def polygon(center, r, sides, cp, corner=True, rot=0.0):
    sides = max(3, int(sides))
    rr = r if corner else r / math.cos(math.pi / sides)
    off = 0.0 if corner else 180.0 / sides
    pts = []
    for k in range(sides):
        ang = math.radians(rot + off + 360.0 * k / sides)
        pts.append(center + cp.u * (rr * math.cos(ang)) + cp.v * (rr * math.sin(ang)))
    return _closed_poly(pts, 0.0)


def _closed_poly(pts, radius):
    n = len(pts)
    if radius <= TOL:
        return [line(pts[i], pts[(i + 1) % n]) for i in range(n)
                if (pts[i] - pts[(i + 1) % n]).Length > TOL]
    edges = []
    tps = []
    for i in range(n):
        p = pts[i]
        ea = (pts[i - 1] - p).normalize()
        eb = (pts[(i + 1) % n] - p).normalize()
        half = math.acos(max(-1.0, min(1.0, ea.dot(eb)))) / 2
        t = radius / math.tan(half)
        bis = (ea + eb).normalize()
        c = p + bis * (radius / math.sin(half))
        t1, t2 = p + ea * t, p + eb * t
        edges.append(arc3(t1, c - bis * radius, t2))
        tps.append((t1, t2))
    out = []
    for i in range(n):
        a = tps[i][1]
        b = tps[(i + 1) % n][0]
        if (a - b).Length > TOL:
            out.append(line(a, b))
        out.append(edges[(i + 1) % n])
    return out


# ------------------------------------------------------------- inspection
def is_line(e):
    return isinstance(e.Curve, Part.Line)


def is_circle(e):
    return isinstance(e.Curve, Part.Circle)


def is_closed(e):
    return e.isClosed()


def extended(e):
    """Edge of the underlying curve: long line or full circle."""
    if is_line(e):
        a = e.Vertexes[0].Point
        d = (e.Vertexes[-1].Point - a).normalize()
        return line(a - d * BIG, a + d * BIG)
    if is_circle(e):
        return Part.Edge(e.Curve)
    return e


def intersections(e1, e2, extend1=False, extend2=False):
    s1 = extended(e1) if extend1 else e1
    s2 = extended(e2) if extend2 else e2
    try:
        sec = s1.section(s2)
        pts = [v.Point for v in sec.Vertexes]
    except Exception:
        pts = []
    if not pts:
        try:
            d, pairs, _ = s1.distToShape(s2)
            if d < 1e-6:
                pts = [p[0] for p in pairs]
        except Exception:
            pass
    return pts


def nearest(points, p):
    return min(points, key=lambda q: (q - p).Length) if points else None


def keypoints(edge):
    """Snap points of an edge: list of (point, kind)."""
    out = []
    if is_closed(edge) and is_circle(edge):
        c = edge.Curve
        out.append((c.Center, "Center"))
        for k in range(4):
            out.append((c.value(k * math.pi / 2), "Quad"))
        return out
    vs = edge.Vertexes
    for v in vs:
        out.append((v.Point, "End"))
    f, l = edge.FirstParameter, edge.LastParameter
    out.append((edge.valueAt((f + l) / 2), "Mid"))
    if is_circle(edge):
        c = edge.Curve
        out.append((c.Center, "Center"))
        for k in range(4):
            t = k * math.pi / 2
            for tt in (t, t + 2 * math.pi, t - 2 * math.pi):
                if f + TOL < tt < l - TOL:
                    out.append((c.value(tt), "Quad"))
                    break
    return out


def tangent_points_from(p, edge):
    """Tangent points on a circle/arc as seen from point p (in the circle plane)."""
    if not is_circle(edge):
        return []
    c = edge.Curve
    n = c.Axis
    q = p - n * (p - c.Center).dot(n)
    d = q - c.Center
    L = d.Length
    r = c.Radius
    if L <= r + TOL:
        return []
    a = math.acos(r / L)
    e1 = V(d).normalize()
    e2 = n.cross(e1)
    return [c.Center + (e1 * math.cos(a) + e2 * (s * math.sin(a))) * r for s in (1, -1)]


def perpendicular_foot(p, edge):
    try:
        d, pairs, _ = Part.Vertex(p).distToShape(extended(edge) if is_line(edge) else edge)
        return pairs[0][1]
    except Exception:
        return None


def circle_circle_tangent(e1, h1, e2, h2):
    """Line tangent to two circles, the one closest to the two pick points."""
    c1, c2 = e1.Curve, e2.Curve
    n = c1.Axis
    C1 = c1.Center
    C2 = c2.Center - n * (c2.Center - C1).dot(n)
    r1, r2 = c1.Radius, c2.Radius
    dv = C2 - C1
    d = dv.Length
    if d < TOL:
        return None
    ex = V(dv).normalize()
    ey = n.cross(ex)
    best = None
    for s in (1, -1):
        cos_t = (r1 - s * r2) / d
        if abs(cos_t) > 1:
            continue
        th = math.acos(cos_t)
        for k in (1, -1):
            nv = ex * math.cos(th) + ey * (k * math.sin(th))
            t1 = C1 + nv * r1
            t2 = C2 + nv * (s * r2)
            score = (t1 - h1).Length + (t2 - h2).Length
            if best is None or score < best[0]:
                best = (score, t1, t2)
    return None if best is None else (best[1], best[2])


# ------------------------------------------------------- fillet / chamfer
def _corner(e1, h1, e2, h2):
    """Corner of two lines: intersection X and unit dirs toward the kept sides."""
    a1 = e1.Vertexes[0].Point
    d1 = (e1.Vertexes[-1].Point - a1).normalize()
    a2 = e2.Vertexes[0].Point
    d2 = (e2.Vertexes[-1].Point - a2).normalize()
    if abs(d1.dot(d2)) > 1 - 1e-9:
        raise ValueError("Lines are parallel")
    pts = intersections(e1, e2, True, True)
    if not pts:
        raise ValueError("Lines do not intersect (not coplanar?)")
    x = pts[0]
    u1 = d1 if (h1 - x).dot(d1) >= 0 else -d1
    u2 = d2 if (h2 - x).dot(d2) >= 0 else -d2
    return x, u1, u2


def _trimmed_line(e, x, u, newpt):
    """Keep the far end of line e (along u from x) and replace the corner end."""
    far = max((v.Point for v in e.Vertexes), key=lambda p: (p - x).dot(u))
    if (far - newpt).dot(u) <= TOL:
        return None
    return line(newpt, far)


def fillet_lines(e1, h1, e2, h2, r):
    x, u1, u2 = _corner(e1, h1, e2, h2)
    th = math.acos(max(-1.0, min(1.0, u1.dot(u2))))
    half = th / 2
    t = r / math.tan(half)
    bis = (u1 + u2).normalize()
    c = x + bis * (r / math.sin(half))
    t1, t2 = x + u1 * t, x + u2 * t
    arc = arc3(t1, c - bis * r, t2)
    return arc, _trimmed_line(e1, x, u1, t1), _trimmed_line(e2, x, u2, t2)


def fillet_general(e1, h1, e2, h2, r):
    """Fillet for any two coplanar edges (lines/arcs) using OCC ChFi2d."""
    try:
        n = None
        for e in (e1, e2):
            if is_circle(e):
                n = e.Curve.Axis
                break
        if n is None:
            raise ValueError
        pl = Part.Plane(h1, n)
        api = Part.ChFi2d.FilletAPI(e1, e2, pl)
        if not api.perform(r):
            raise ValueError("Fillet failed")
        f = api.result((h1 + h2) * 0.5)[0]
        # trim ourselves so the picked sides are kept (as in Mastercam)
        ends = [v.Point for v in f.Vertexes]
        t1 = min(ends, key=lambda p: e1.distToShape(Part.Vertex(p))[0])
        t2 = min(ends, key=lambda p: e2.distToShape(Part.Vertex(p))[0])
        return f, trim_to_point(e1, h1, t1), trim_to_point(e2, h2, t2)
    except ValueError:
        raise
    except Exception as ex:
        raise ValueError(str(ex))


def chamfer_lines(e1, h1, e2, h2, method, d1, d2=0.0, ang=45.0, width=0.0):
    x, u1, u2 = _corner(e1, h1, e2, h2)
    th = math.acos(max(-1.0, min(1.0, u1.dot(u2))))
    if method == "Distance":
        a, b = d1, d1
    elif method == "2 Distances":
        a, b = d1, d2
    elif method == "Distance/Angle":
        g = math.radians(ang)
        a = d1
        b = d1 * math.sin(g) / math.sin(math.pi - th - g)
    else:  # Width
        a = b = width / (2 * math.sin(th / 2))
    p1, p2 = x + u1 * a, x + u2 * b
    return line(p1, p2), _trimmed_line(e1, x, u1, p1), _trimmed_line(e2, x, u2, p2)


# ------------------------------------------------------------------ trim
def _rebuild(e, f, l):
    if is_line(e):
        return line(e.valueAt(f), e.valueAt(l))
    if is_circle(e):
        return Part.ArcOfCircle(e.Curve, f, l).toShape()
    return e.Curve.toShape(f, l)


def _param(e, p):
    t = e.Curve.parameter(p)
    if is_circle(e):
        f, l = e.FirstParameter, e.LastParameter
        while t < f - 1e-9:
            t += 2 * math.pi
        while t > f + 2 * math.pi + 1e-9:
            t -= 2 * math.pi
    return t


def trim_to_point(e, keep, x):
    """Trim/extend edge e to point x (on its curve), keeping the side of 'keep'."""
    if is_line(e):
        a = e.Vertexes[0].Point
        d = (e.Vertexes[-1].Point - a).normalize()
        tx = (x - a).dot(d)
        tk = (keep - a).dot(d)
        ends = [0.0, (e.Vertexes[-1].Point - a).Length]
        side = [t for t in ends if (t - tx) * (tk - tx) > 0]
        if not side:
            return None
        far = max(side, key=lambda t: abs(t - tx))
        return line(a + d * tx, a + d * far)
    if is_circle(e):
        if e.isClosed():
            return None
        f, l = e.FirstParameter, e.LastParameter
        tk = _param(e, keep)
        tx = _param(e, x)
        if f + TOL < tx < l - TOL:
            return _rebuild(e, tx, l) if tk > tx else _rebuild(e, f, tx)
        # extension: tx lies past one end (modulo 2pi)
        past_end = tx - l
        before_start = f + 2 * math.pi - tx
        if past_end <= before_start:
            return _rebuild(e, f, tx)
        return _rebuild(e, tx - 2 * math.pi, l)
    return None


def trim_curve_point(e, x):
    """Project a point onto the (extended) curve of e."""
    d, pairs, _ = Part.Vertex(x).distToShape(extended(e))
    return pairs[0][1]


def divide(e, pick, others):
    """Remove the piece of e between the intersections around 'pick'."""
    ts = []
    for o in others:
        for p in intersections(e, o):
            ts.append(_param(e, p))
    f, l = e.FirstParameter, e.LastParameter
    tp = _param(e, pick)
    if e.isClosed():
        ts = sorted(set(round(t, 9) for t in ts))
        if len(ts) < 2:
            return None
        # circle: keep the arc that does not contain the pick
        lo = max([t for t in ts if t <= tp], default=ts[-1] - 2 * math.pi)
        hi = min([t for t in ts if t > tp], default=ts[0] + 2 * math.pi)
        return [_rebuild(e, hi, lo + 2 * math.pi)]
    ts = sorted(t for t in ts if f + TOL < t < l - TOL)
    lo = max([t for t in ts if t <= tp], default=f)
    hi = min([t for t in ts if t > tp], default=l)
    out = []
    if lo - f > TOL:
        out.append(_rebuild(e, f, lo))
    if l - hi > TOL:
        out.append(_rebuild(e, hi, l))
    return out


def signature(shape, nd=6):
    pts = []
    for v in shape.Vertexes:
        pts.append(tuple(round(c, nd) for c in v.Point))
    for e in shape.Edges:
        m = e.valueAt((e.FirstParameter + e.LastParameter) / 2)
        pts.append(tuple(round(c, nd) for c in m))
    return tuple(sorted(pts))

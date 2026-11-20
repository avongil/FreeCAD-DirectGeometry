"""Construction plane (Mastercam "Cplane").

Mouse picks that do not snap to existing geometry land on the active
construction plane, at its depth (Mastercam's "Z" depth). Typed points are
global, so geometry can be placed anywhere in 3D regardless of the Cplane.
2D entities that need a plane (circles, arcs, rectangles, polygons) are
built parallel to the Cplane.
"""

import math

import FreeCAD as App

V = App.Vector

# name: (u, v, n) with u x v = n
STANDARD = {
    "Top": (V(1, 0, 0), V(0, 1, 0), V(0, 0, 1)),
    "Front": (V(1, 0, 0), V(0, 0, 1), V(0, -1, 0)),
    "Right": (V(0, 1, 0), V(0, 0, 1), V(1, 0, 0)),
    "Back": (V(-1, 0, 0), V(0, 0, 1), V(0, 1, 0)),
    "Left": (V(0, -1, 0), V(0, 0, 1), V(-1, 0, 0)),
    "Bottom": (V(1, 0, 0), V(0, -1, 0), V(0, 0, -1)),
}


class CPlane:
    def __init__(self):
        self.name = "Top"
        self.u, self.v, self.n = (V(a) for a in STANDARD["Top"])
        self.base = V(0, 0, 0)   # a point on the plane at depth 0
        self.depth = 0.0

    # --- setup -------------------------------------------------------
    def set_standard(self, name):
        u, v, n = STANDARD[name]
        self.set_axes(u, v, n, V(0, 0, 0), name)

    def set_axes(self, u, v, n, base, name="Custom"):
        self.u = V(u).normalize()
        self.n = V(n).normalize()
        self.v = self.n.cross(self.u).normalize()
        self.base = V(base)
        self.name = name

    def set_from_rotation(self, rot, base=None, name="Gview"):
        u = rot.multVec(V(1, 0, 0))
        v = rot.multVec(V(0, 1, 0))
        n = rot.multVec(V(0, 0, 1))
        self.set_axes(u, v, n, base if base is not None else self.base, name)

    # --- queries -----------------------------------------------------
    @property
    def origin(self):
        return self.base + self.n * self.depth

    def to_local(self, p):
        d = p - self.origin
        return d.dot(self.u), d.dot(self.v), d.dot(self.n)

    def to_global(self, x, y, z=0.0):
        return self.origin + self.u * x + self.v * y + self.n * z

    def angle_of(self, vec):
        """CCW angle (degrees) of a vector measured in the Cplane."""
        return math.degrees(math.atan2(vec.dot(self.v), vec.dot(self.u)))

    def direction(self, deg):
        a = math.radians(deg)
        return self.u * math.cos(a) + self.v * math.sin(a)

    def flatten(self, p, through):
        """Project p onto the plane parallel to the Cplane that contains 'through'."""
        return p - self.n * (p - through).dot(self.n)

    def intersect_ray(self, p0, d, through=None):
        """Point where the ray p0 + t*d hits the plane (through 'through' or at depth)."""
        o = through if through is not None else self.origin
        den = d.dot(self.n)
        if abs(den) < 1e-9:
            return self.flatten(p0, o)
        t = (o - p0).dot(self.n) / den
        return p0 + d * t

    def rotation(self):
        m = App.Matrix(self.u.x, self.v.x, self.n.x, 0,
                       self.u.y, self.v.y, self.n.y, 0,
                       self.u.z, self.v.z, self.n.z, 0,
                       0, 0, 0, 1)
        return App.Placement(m).Rotation

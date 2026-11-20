"""FreeCAD command registration."""

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part

from . import gnomon, session, tools_create as tc, tools_edit as te

ICONS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")


def icon(name):
    return os.path.join(ICONS, name + ".svg")


class _ToolCommand:
    def __init__(self, tool_cls, icon_name, menu, tip, accel=""):
        self.tool_cls, self.icon_name, self.menu, self.tip, self.accel = tool_cls, icon_name, menu, tip, accel

    def GetResources(self):
        r = {"Pixmap": icon(self.icon_name), "MenuText": self.menu, "ToolTip": self.tip}
        if self.accel:
            r["Accel"] = self.accel
        return r

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        session.get().start_tool(self.tool_cls())


class _FuncCommand(_ToolCommand):
    def __init__(self, func, icon_name, menu, tip, accel="", needs_doc=True):
        super().__init__(None, icon_name, menu, tip, accel)
        self.func, self.needs_doc = func, needs_doc

    def IsActive(self):
        return App.ActiveDocument is not None or not self.needs_doc

    def Activated(self):
        self.func()


def make_sketch():
    """Turn the selected geometry into a Sketcher sketch placed where it is."""
    import Draft
    doc = App.ActiveDocument
    objs = [o for o in Gui.Selection.getSelection() if o.isDerivedFrom("Part::Feature")
            and o.Shape.Edges]
    if not objs:
        App.Console.PrintWarning("DirectGeo: select the lines/arcs/circles to put in the sketch\n")
        session.get().message("Select the geometry for the sketch first")
        return
    edges = [e for o in objs for e in o.Shape.Edges]
    try:
        planar = Part.Compound(edges).isPlanar()
    except Exception:
        planar = True   # let Draft decide
    if not planar:
        session.get().message("The selected geometry is not in one plane")
        App.Console.PrintError("DirectGeo: Make Sketch needs geometry that lies in one plane\n")
        return
    doc.openTransaction("Make Sketch")
    try:
        sk = Draft.make_sketch(objs, autoconstraints=True, name="Sketch")
        if sk is None:
            raise ValueError("the selected geometry is not in one plane")
        doc.commitTransaction()
    except Exception as ex:
        doc.abortTransaction()
        session.get().message("Could not make a sketch: %s" % ex)
        App.Console.PrintError("DirectGeo: Make Sketch failed: %s\n" % ex)
        return
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, sk.Name)
    session.get().message("%s made from %d entities" % (sk.Label, len(objs)))


def _cplane(name):
    def f():
        s = session.get()
        s.show_bars()
        s.set_cplane(name)
    return f


CREATE = [
    ("DG_Point", tc.PointTool, "point", "Point Position", "Create points at picked or typed positions"),
    ("DG_Line", tc.LineTool, "line", "Line Endpoints", "Create lines by two endpoints, with length/angle, H/V and tangency"),
    ("DG_LineParallel", tc.ParallelTool, "parallel", "Line Parallel", "Create a line parallel to another at a distance"),
    ("DG_Circle", tc.CircleTool, "circle", "Circle Center Point", "Create a circle from its center and radius/diameter"),
    ("DG_ArcPolar", tc.ArcPolarTool, "arcpolar", "Arc Polar", "Create an arc from center, radius, start and end angles"),
    ("DG_ArcEndpoints", tc.ArcEndpointsTool, "arcends", "Arc Endpoints", "Create an arc from two endpoints and a point on the arc"),
    ("DG_Arc3Points", tc.Arc3PointsTool, "arc3", "Arc 3 Points", "Create an arc through three points"),
    ("DG_Rectangle", tc.RectangleTool, "rectangle", "Rectangle", "Create a rectangle by two corners or by base point"),
    ("DG_Polygon", tc.PolygonTool, "polygon", "Polygon", "Create a regular polygon"),
    ("DG_Fillet", te.FilletTool, "fillet", "Fillet Entities", "Round the corner between two entities"),
    ("DG_Chamfer", te.ChamferTool, "chamfer", "Chamfer Entities", "Chamfer the corner between two lines"),
]
EDIT = [
    ("DG_Trim", te.TrimTool, "trim", "Trim/Break/Extend", "Trim 1, 2 or 3 entities, divide, or trim to a point"),
    ("DG_CloseArc", te.CloseArcTool, "closearc", "Close Arc", "Turn an arc into a full circle"),
]
XFORM = [
    ("DG_DynamicTransform", gnomon.DynamicTransformTool, "gnomon", "Dynamic Transform",
     "Move, copy or rotate entities with the on-screen gnomon (Mastercam X4 style)"),
]

CREATE_NAMES = [c[0] for c in CREATE]
EDIT_NAMES = [c[0] for c in EDIT] + ["DG_DeleteDuplicates"]
XFORM_NAMES = [c[0] for c in XFORM]
OUTPUT_NAMES = ["DG_MakeSketch"]
PLANE_NAMES = ["DG_CplaneTop", "DG_CplaneFront", "DG_CplaneRight", "DG_CplaneGview", "DG_ToggleAxes"]


def register():
    for name, cls, ic, menu, tip in CREATE + EDIT + XFORM:
        Gui.addCommand(name, _ToolCommand(cls, ic, menu, tip))
    Gui.addCommand("DG_DeleteDuplicates", _FuncCommand(
        te.delete_duplicates, "deldup", "Delete Duplicates",
        "Delete entities that exactly overlap another (selection, or all)"))
    Gui.addCommand("DG_MakeSketch", _FuncCommand(
        make_sketch, "makesketch", "Make Sketch",
        "Make a Sketcher sketch from the selected geometry, placed on its plane\n"
        "(ready for Pad, Pocket or Extrude). The original entities are kept."))
    for n in ("Top", "Front", "Right", "Gview"):
        Gui.addCommand("DG_Cplane" + n, _FuncCommand(
            _cplane(n), "cplane" + n.lower(), "Cplane " + n,
            "Set the construction plane to " + n + (" (facing the screen)" if n == "Gview" else "")))
    Gui.addCommand("DG_ToggleAxes", _FuncCommand(
        lambda: session.get().toggle_axes(), "axes", "System Axes", "Show or hide the system axes", "F9"))

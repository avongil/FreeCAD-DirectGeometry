# Direct Geometry workbench: Mastercam X style direct 2D geometry in 3D space.

import FreeCADGui as Gui


class DirectGeoWorkbench(Gui.Workbench):
    MenuText = "Direct Geometry"
    ToolTip = "Direct (no history) 2D geometry in 3D space, Mastercam X style"

    def __init__(self):
        # FreeCAD runs this file without module globals in class scope: import here
        import os
        import directgeo
        root = os.path.dirname(os.path.dirname(os.path.abspath(directgeo.__file__)))
        self.__class__.Icon = os.path.join(root, "icons", "DirectGeo.svg")

    def Initialize(self):
        from directgeo import commands
        commands.register()
        self.appendToolbar("DG Create", commands.CREATE_NAMES)
        self.appendToolbar("DG Edit", commands.EDIT_NAMES)
        self.appendToolbar("DG Xform", commands.XFORM_NAMES)
        self.appendToolbar("DG Planes", commands.PLANE_NAMES)
        self.appendToolbar("DG Output", commands.OUTPUT_NAMES)
        self.appendMenu("Create", commands.CREATE_NAMES)
        self.appendMenu("&Edit", ["Separator"] + commands.EDIT_NAMES)
        self.appendMenu("Xform", commands.XFORM_NAMES)
        self.appendMenu("Create", ["Separator"] + commands.OUTPUT_NAMES)
        self.appendMenu(["&View", "Cplane"], commands.PLANE_NAMES)

    def Activated(self):
        from directgeo import session
        session.get().show_bars()

    def Deactivated(self):
        from directgeo import session
        session.get().hide_bars()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(DirectGeoWorkbench())

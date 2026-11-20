<p align="center">
  <img src="icons/DirectGeo.svg" width="96" alt="Direct Geometry icon">
</p>

<h1 align="center">Direct Geometry</h1>

<p align="center">
  <b>Mastercam X style drawing in 3D space, for FreeCAD.</b>
  <br>
  <a href="https://avongil.github.io/FreeCAD-DirectGeometry/"><b>Manual</b></a> ·
  <a href="#install">Install</a> ·
  <a href="#commands">Commands</a>
  <br><br>
  <img alt="Proof of concept" src="https://img.shields.io/badge/status-proof%20of%20concept-e0a020">
  <img alt="License LGPL-2.1-or-later" src="https://img.shields.io/badge/license-LGPL--2.1--or--later-5a6375">
</p>

---

> **This is a proof of concept.** It's a bit rough around the edges, but it works.

My favorite direct CAD interface is the Mastercam X style interface. It was
gone after X9, but it's still loved by many! This workbench brings that ease of
drawing in 3D space to FreeCAD: 2D geometry is created directly in 3D space
(no sketch, no history), on any construction plane at any depth, and a Dynamic
Transform gnomon (Mastercam X4 style) moves, copies and rotates it. When you
want a solid, **Make Sketch** turns the wireframe into a regular Sketcher
sketch ready to Pad, Pocket or Extrude.

Tested on the FreeCAD weekly development build 26.3.0dev (2026-09-16).

## Install

1. In FreeCAD open the Python console (View > Panels > Python console) and run
   `App.getUserAppDataDir()`. It prints your user folder, for example
   `~/.local/share/FreeCAD/v26-3/` on Linux or `%APPDATA%\FreeCAD\v1-1\` on Windows.
2. Download this repository (**Code > Download ZIP**, or `git clone`) and put
   the folder holding `InitGui.py` into the `Mod` subfolder of that folder,
   creating `Mod` if needed. The result must be
   `<user folder>/Mod/DirectGeo/InitGui.py` (the folder name itself doesn't
   matter); directly in the user folder it is not found.
3. Restart FreeCAD and choose **Direct Geometry** in the workbench selector.

## The screen

- **AutoCursor bar**: live X/Y/Z of the cursor. Click X, Y or Z to lock that
  value (red). Type values and press Enter to place a point. The **Fast point**
  box takes `2,2,3` + Enter for global X2 Y2 Z3; `2,2` is a point on the Cplane.
  Expressions and units work (`1in`, `25.4/2`). **AutoCursor** picks the snap
  types (Origin, Point, End, Mid, Center, Quad, Intersection, Tangent,
  Perpendicular, Horiz/Vert, Nearest); **Only** limits snapping to one type.
- **Ribbon bar**: changes with each command. Fields edit the live (light blue)
  entity when you press Enter; the label buttons lock a value. **+** keeps the
  entity and continues, **✔** (or Esc) keeps it and ends the command.
  Committed geometry turns green.
- **Cplane bar** (third row at the top): **MODE: 2D / MODE: 3D** button
  (click to switch). In 2D, every clicked or snapped point is put on the
  Cplane at Z depth, so snapping to existing geometry draws on top of it at
  that depth. In 3D, points stay exactly where they snap. Typed coordinates
  are always used as typed. Dynamic Transform, trim and fillet ignore the mode.
  Then Cplane (Top, Front, Right, Back, Left, Bottom,
  Gview = facing the screen, Gnomon) and Z depth. Free clicks land on the
  Cplane at that depth; circles, arcs, rectangles and polygons are drawn
  parallel to it. **Axes (F9)** shows the system axes.

## Entity properties

Click an entity (with no command running) and FreeCAD's property view shows
it. The **Data** tab has a **Geometry** group you can edit directly:

- Point: Position (X, Y, Z)
- Line: Start Point, End Point, Length, Angle (XY plane)
- Circle: Center, Radius, Diameter, Normal
- Arc: Center, Radius, Diameter, Start Angle, End Angle, Normal (Start/End
  Point shown read only)

Edits reshape the entity at once and can be undone. The **View** tab holds the
display settings: Line Color, Line Width (thickness), Point Color, Point Size,
Draw Style. Dynamic Transform keeps each entity's own colour and width, and
copies take theirs from the original. Files stay plain FreeCAD Part objects.

## Commands

Create: Point, Line Endpoints (multi, length/angle, horizontal/vertical,
tangent to two circles; tangent and perpendicular snaps from the first point),
Line Parallel, Circle Center Point, Arc Polar, Arc Endpoints, Arc 3 Points,
Rectangle (2 points, or lock width and height to place by base point; center
anchor, corner radius, rotation), Polygon (radius to corner or flats, or
Flat to Flat for even side counts; dimmed for odd counts such as a triangle), Fillet (lines and arcs, trim),
Chamfer (Distance, 2 Distances, Distance/Angle, Width).

Output: **Make Sketch** (DG Output toolbar, end of the Create menu). Select
coplanar entities and click it: you get a Sketcher sketch placed on their plane
(any Cplane or depth), with coincident/horizontal/vertical constraints added,
ready for Part Extrude or PartDesign Pad/Pocket. The entities are kept.

Edit: Trim/Break/Extend (1, 2, 3 entities, Divide, To Point), Close Arc,
Delete Duplicates. Delete is FreeCAD's normal Del key.

Xform: **Dynamic Transform**. Select entities (or start the command and select,
then Enter), pick the gnomon origin or press Enter for the centre of the
selection. Then click a handle, move the mouse, click again:
arrow = move along U/V/W, square = move in that plane, arc ball = rotate,
centre ball = move to a snapped point. AutoCursor snapping works while
dragging. dU/dV/dW and Angle edit the last move. Move or Copy (with a number
of copies), Angle Step / Dist Step for increments, **Gnomon Only** to
reposition or re-orient the gnomon, **Cplane = Gnomon** to draw on the
gnomon's plane (2D geometry on any 3D plane).

## Not in this version (yet)

Arc tangent variants, letters/fonts, ellipse, break many/at intersection,
drafting dimensions, 3D solids. Units follow the FreeCAD document (mm by
default; type `in` after a value for inches).

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).

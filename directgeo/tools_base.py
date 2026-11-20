"""Base class for interactive commands.

A command creates "live" entities (light blue) that stay editable from the
ribbon bar until the next entity is started, Apply (+) or OK is pressed, or
Esc ends the command. Then they turn green and become plain geometry.
"""

import FreeCAD as App

from . import entities


class Tool:
    title = "Command"
    construction = True     # 2D mode flattens this tool's points onto the Cplane

    def __init__(self):
        self.s = None
        self.live = []
        self.locks = {}
        self.editing = None
        self.done = False
        self._txn = False

    # ---- lifecycle -------------------------------------------------------
    def begin(self, session):
        self.s = session
        self.setup()

    def setup(self):
        pass

    def end(self):
        self.commit()
        self.cleanup()

    def cleanup(self):
        pass

    def ribbon(self):
        return []

    def prompt(self):
        return ""

    @property
    def cp(self):
        return self.s.cplane

    @property
    def doc(self):
        return App.ActiveDocument

    # ---- hooks -------------------------------------------------------------
    def uses_snap(self):
        return True

    def wants_clicks(self):
        return True

    def from_point(self):
        return None

    def snap_exclude(self):
        return list(self.live) if self.editing else []

    def on_move(self, p, snap):
        pass

    def on_point(self, p, snap):
        pass

    def on_enter(self):
        pass

    def on_field(self, key, val):
        pass

    def on_button(self, key):
        if key.startswith("edit"):
            if not self.live:
                self.s.message("Nothing live to edit")
                return
            self.editing = key

    # ---- preview -------------------------------------------------------------
    def preview(self, shapes):
        self.s.preview.set_shapes(shapes)

    def clear_preview(self):
        self.s.preview.clear()

    def set_field(self, key, val):
        self.s.ribbon.set_value(key, val)

    # ---- live entities ---------------------------------------------------
    def open_txn(self):
        if not self._txn:
            self.doc.openTransaction("Direct " + self.title)
            self._txn = True

    def close_txn(self):
        if self._txn:
            self.doc.commitTransaction()
            self._txn = False

    def set_live(self, shapes):
        self.live = [o for o in self.live if entities.alive(o)]
        self.open_txn()
        while len(self.live) > len(shapes):
            o = self.live.pop()
            self.doc.removeObject(o.Name)
        for i, sh in enumerate(shapes):
            if i < len(self.live):
                entities.set_shape(self.live[i], sh)
            else:
                self.live.append(entities.make(sh, live=True))
        self.doc.recompute()

    def commit(self):
        for o in self.live:
            if entities.alive(o):
                entities.style(o, entities.DONE)
        self.live = []
        self.editing = None
        self.close_txn()

    def reset(self):
        pass

    # ---- ribbon actions -------------------------------------------------
    def apply(self):
        self.commit()
        self.reset()
        self.clear_preview()

    def finish(self):
        self.commit()
        self.clear_preview()
        self.s.request_end(self)

    def escape(self):
        self.finish()


class PickTool(Tool):
    """Commands that act on existing entities (fillet, trim, ...)."""
    construction = False

    def picked_edge(self, snap):
        e = snap.edge
        if e is None:
            self.s.message("Select an entity")
        return e

    def modify(self, label, fn):
        doc = self.doc
        doc.openTransaction("Direct " + label)
        try:
            fn()
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            raise
        doc.recompute()

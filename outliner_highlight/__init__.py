"""outliner-highlight — keep the active object in view in the Outliner.

What the user asked for, and what Blender already does itself
------------------------------------------------------------

The paid add-on this replaces does three things: scroll the Outliner to the
object you just selected, expand its parent collections, and optionally collapse
everything else. Two of the three are native in Blender 5.x —
``SpaceOutliner.scroll_to_active`` ("Scroll the active item into view when it
changes outside of the Outliner") is that feature, spelled out. Verified on
5.2.1 by reading the property off ``bpy.types.SpaceOutliner.bl_rna``.

What is *not* native is the third: collapsing the collections that have nothing
to do with the selection. That is the reason this add-on exists, and it is the
part the rest of these modules are about.

The recipe, measured rather than assumed
----------------------------------------

Both screenshots and return values were taken in a live 5.2.1 session with a
deliberately deep tree (``Root > A > B > C > object`` plus siblings):

* ``outliner.show_active()`` alone expands the whole parent chain, scrolls the
  row into view and highlights it. One call, no arguments.
* ``outliner.show_one_level(open=False)`` collapses *every* entry by one level,
  and because it applies to all entries a single call flattens the entire tree.
* ``outliner.item_openclose(all=True)`` looks like the right tool and is not:
  without an input event it returns ``PASS_THROUGH`` and changes nothing.
* So the recipe is ``show_one_level(open=False)`` followed by ``show_active()``:
  collapse everything, then let Blender re-reveal the one path that matters.
  That is exactly "expand the parents, collapse the rest", in two calls.

Where the switch lives, and why not where it belongs
----------------------------------------------------

A per-Outliner property on ``SpaceOutliner`` — next to ``use_sync_select`` —
would be the honest place for it. It cannot be done: ``SpaceOutliner`` rejects
Python-defined properties. ``space.auto_highlight = bpy.props.BoolProperty()``
is accepted at class level but never reaches ``bl_rna.properties``, and setting
it on a live space raises "attribute 'ah_probe' is read-only". The type does not
carry IDProperties either, so ``space.keys()`` raises "this type doesn't support
IDProperties". Both measured on 5.2.1.

The state therefore lives on the Scene (see :mod:`properties`), which is
writable, is saved into the .blend, and gives the same user-visible result: one
switch per file, drawn in the Outliner's Filters popover.

Registration order
------------------

Properties first, then the UI that draws them, then the watcher that reads them.
:func:`unregister` undoes it in reverse, and the watcher's timer goes first —
a timer that outlives its module is how you get a traceback per tick from a
callback referencing freed classes.
"""

from __future__ import annotations

bl_info = {
    "name": "Outliner Auto-Highlight",
    "description": (
        "Follows the active object in the Outliner: expands its parent "
        "collections and can collapse everything else."
    ),
    "author": "sc3d.studio",
    "version": (0, 1, 1),
    # 4.2 rather than the 3.3 this code would probably still run on: 4.2 is what
    # the extension manifest can declare, and shipping two different minimums for
    # the same source is a lie waiting to drift. Only 5.2.1 has actually been run
    # -- see docs/technical-notes.md.
    "blender": (4, 2, 0),
    "location": "Outliner > Filters",
    "category": "User Interface",
}

from . import properties as _properties
from . import ui as _ui
from . import watcher as _watcher

_REGISTERED = False


def register() -> None:
    """Register the add-on. Blender calls this with no arguments."""
    global _REGISTERED
    if _REGISTERED:
        return

    _properties.register()
    _ui.register()
    _watcher.register()
    _REGISTERED = True


def unregister() -> None:
    global _REGISTERED
    if not _REGISTERED:
        return

    # The timer first: it is the only piece that can fire on its own, and every
    # callback it runs touches the classes unregistered below.
    _watcher.unregister()
    _ui.unregister()
    _properties.unregister()
    _REGISTERED = False

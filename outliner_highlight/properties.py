"""Scene flags and add-on preferences.

Why the two switches sit on the Scene
-------------------------------------

``__init__.py`` has the full measurement. Short version: ``SpaceOutliner``
refuses Python-defined properties, so "per Outliner" is off the table in Blender
5.2, and the Scene is the nearest writable thing that is saved into the .blend.
The user-visible contract is unchanged — one switch per file, drawn in the
Outliner's Filters popover — only the granularity is coarser than the paid
add-on advertises.

Consequence worth knowing: the flag is per *file*, not per *editor*. Two
Outliner Areas in one file cannot disagree, and a second window showing the same
file follows along. That is the cost of the RNA restriction, not a design
preference.

Defaulting for new files
------------------------

A property default has to be a constant, so the "start every new file with this
on" preference cannot be expressed as a default value. It is applied in a
``load_post`` handler instead, and only when ``bpy.data.filepath`` is empty —
which is exactly the case for a file created from the startup file rather than
opened. A file the user has saved keeps its own saved state, which is what makes
the rule safe to run on every load.
"""

from __future__ import annotations

import bpy

_SCENE_PROPS = {
    "outliner_auto_highlight": dict(
        name="Auto-Highlight",
        description=(
            "Keep the active object in view: scroll the Outliner to it and "
            "expand its parent collections"
        ),
        default=False,
    ),
    "outliner_auto_highlight_collapse": dict(
        name="Collapse Other Collections",
        description=(
            "Also collapse every collection that does not contain the active object"
        ),
        default=False,
    ),
}


def _flag_changed(self, context):
    """Let the watcher re-evaluate instead of working from a stale key.

    Ticking the box has to reveal the active object *now*, but a property update
    callback is the wrong place to run operators from — the timer is at most one
    interval away, so this only drops the cached keys and lets the next tick do
    the work through the normal, already-tested path.
    """
    from . import watcher

    watcher.invalidate()


class OutlinerHighlightPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    enabled_on_startup: bpy.props.BoolProperty(
        name="On in new files",
        description=(
            "Start with Auto-Highlight enabled in files created from the "
            "startup file. Files saved with their own setting keep it"
        ),
        default=True,
    )
    collapse_on_startup: bpy.props.BoolProperty(
        name="Collapse in new files",
        description="Start with Collapse Other Collections enabled in new files",
        default=True,
    )
    interval: bpy.props.FloatProperty(
        name="Check Interval",
        description=(
            "How often the active object is compared against the last one seen, "
            "in seconds. A tick costs one attribute read per window; the "
            "Outliner is only touched when the active object actually changed"
        ),
        default=0.15,
        min=0.05,
        max=2.0,
        precision=2,
    )
    header_button: bpy.props.BoolProperty(
        name="Button in the Outliner header",
        description="Also draw the toggle in the Outliner header, not only in Filters",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(heading="New files")
        col.prop(self, "enabled_on_startup")
        sub = col.row()
        sub.enabled = self.enabled_on_startup
        sub.prop(self, "collapse_on_startup")

        layout.separator()
        layout.prop(self, "interval")
        layout.prop(self, "header_button")

        layout.separator()
        layout.operator(
            "outliner.auto_highlight_apply_all",
            text="Enable on Every Scene in this File",
            icon='SCENE_DATA',
        )


def preferences():
    """The preferences of this add-on, or None when it is not registered."""
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def _load_post(_dummy):
    """Give a brand-new file the startup preference; leave opened files alone."""
    if bpy.data.filepath:
        return
    prefs = preferences()
    if prefs is None or not prefs.enabled_on_startup:
        return

    for scene in bpy.data.scenes:
        scene.outliner_auto_highlight = True
        scene.outliner_auto_highlight_collapse = prefs.collapse_on_startup

    from . import watcher

    watcher.invalidate()


def register() -> None:
    for name, spec in _SCENE_PROPS.items():
        setattr(bpy.types.Scene, name, bpy.props.BoolProperty(update=_flag_changed, **spec))
    bpy.utils.register_class(OutlinerHighlightPreferences)
    bpy.app.handlers.load_post.append(_load_post)


def unregister() -> None:
    try:
        bpy.app.handlers.load_post.remove(_load_post)
    except (ValueError, RuntimeError):
        pass
    bpy.utils.unregister_class(OutlinerHighlightPreferences)
    for name in _SCENE_PROPS:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)

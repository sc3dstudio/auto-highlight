"""Where the switches are drawn, and the two manual escape hatches.

The Filters popover is the same home the paid add-on uses, and it is the right
one: ``OUTLINER_PT_filter`` is a normal panel, so ``append`` puts our rows inside
the existing Filters dropdown instead of adding a second place to look. The
header button is a convenience on top and can be turned off in the preferences —
the Outliner header is a crowded strip and the toggle does not belong there for
everyone.

Both draw functions bail out when the Scene property is missing. That is not
paranoia: the append survives a few milliseconds longer than the property on
unregister, and a panel that draws a property which no longer exists raises on
every redraw.
"""

from __future__ import annotations

import bpy

_SYNC_ICON = 'ZOOM_SELECTED'  # the same "show selected" idea as Blender's own "."
_COLLAPSE_ICON = 'TRIA_DOWN'


class OUTLINER_OT_auto_highlight_sync(bpy.types.Operator):
    bl_idname = "outliner.auto_highlight_sync"
    bl_label = "Reveal Active Object Now"
    bl_description = (
        "Run Auto-Highlight immediately instead of waiting for the active "
        "object to change"
    )
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'OUTLINER'

    def execute(self, context):
        from . import watcher

        watcher.invalidate()
        watcher.sync_all()
        return {'FINISHED'}


class OUTLINER_OT_auto_highlight_apply_all(bpy.types.Operator):
    bl_idname = "outliner.auto_highlight_apply_all"
    bl_label = "Enable Auto-Highlight on Every Scene"
    bl_description = (
        "Turn Auto-Highlight on for every Scene in this file. Useful when a "
        "file was authored before the add-on was enabled"
    )
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from . import properties, watcher

        prefs = properties.preferences()
        collapse = prefs.collapse_on_startup if prefs else False
        for scene in bpy.data.scenes:
            scene.outliner_auto_highlight = True
            scene.outliner_auto_highlight_collapse = collapse

        watcher.invalidate()
        self.report(
            {'INFO'},
            f"Auto-Highlight enabled on {len(bpy.data.scenes)} scene(s)",
        )
        return {'FINISHED'}


def _draw_filter(self, context):
    """Rows inside Outliner > Filters."""
    scene = context.scene
    if scene is None or not hasattr(scene, "outliner_auto_highlight"):
        return

    layout = self.layout
    layout.separator()

    col = layout.column(align=True)
    col.prop(scene, "outliner_auto_highlight", text="Auto-Highlight", icon=_SYNC_ICON)

    # The second switch only means anything once the first one is on, which is
    # what the paid add-on does too — greyed out rather than hidden, so the
    # feature stays discoverable.
    collapse = col.row()
    collapse.enabled = scene.outliner_auto_highlight
    collapse.prop(
        scene,
        "outliner_auto_highlight_collapse",
        text="Collapse Others",
        icon=_COLLAPSE_ICON,
    )

    action = layout.row()
    action.enabled = scene.outliner_auto_highlight
    action.operator("outliner.auto_highlight_sync")


def _draw_header(self, context):
    """One compact toggle at the end of the Outliner header."""
    from . import properties

    prefs = properties.preferences()
    if prefs is not None and not prefs.header_button:
        return

    scene = context.scene
    if scene is None or not hasattr(scene, "outliner_auto_highlight"):
        return

    layout = self.layout
    layout.separator()
    layout.prop(
        scene,
        "outliner_auto_highlight",
        text="",
        icon=_SYNC_ICON,
        toggle=True,
    )


_CLASSES = (
    OUTLINER_OT_auto_highlight_sync,
    OUTLINER_OT_auto_highlight_apply_all,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.OUTLINER_PT_filter.append(_draw_filter)
    bpy.types.OUTLINER_HT_header.append(_draw_header)


def unregister() -> None:
    try:
        bpy.types.OUTLINER_HT_header.remove(_draw_header)
    except (ValueError, RuntimeError):
        pass
    try:
        bpy.types.OUTLINER_PT_filter.remove(_draw_filter)
    except (ValueError, RuntimeError):
        pass
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

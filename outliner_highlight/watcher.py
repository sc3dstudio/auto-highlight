"""The thing that notices. Polls, because there is nothing to subscribe to.

Why a timer and not a handler
-----------------------------

``depsgraph_update_post`` fires for every dependency-graph evaluation — a mouse
drag over the viewport is hundreds of them — and running an operator from inside
it is how you get re-entrant updates and a frozen UI. A repeating timer is the
safe shape: it runs in the main loop between events, it does not run at all
while a modal operator is active (so a transform or a box-select is never fought
with), and the work per tick is one attribute read per window.

What is compared, and why not the selection
-------------------------------------------

The trigger is the *active object*, keyed by its pointer rather than its name.
Name would be the obvious key and it is the wrong one: renaming the active
object in the Outliner (F2) would then read as a change, and with Collapse Other
Collections on, a rename would flatten the tree. A pointer is stable across a
rename and changes on a real switch. The address-reuse case — object deleted and
another allocated at the same address, in the same tick — is what the deleted
object's own removal covers well enough for a view convention.

Multi-selection deliberately does not trigger anything: the Outliner highlights
the active object, so extending a selection or deselecting does not move the
thing being followed.

Both operators, and the order they run in
-----------------------------------------

``show_one_level(open=False)`` collapses every entry, then ``show_active()``
re-expands the single path down to the active object and scrolls to it. See
``__init__.py`` for the measurements behind that recipe, including why
``item_openclose`` is not used.
"""

from __future__ import annotations

import traceback

import bpy

# The Outliner display modes that draw a collection tree. "Show active" has
# nothing to reveal in LIBRARIES, DATA_API or ORPHAN_DATA, and running it there
# would touch an editor whose rows are not the ones being followed.
_TREE_MODES = {"VIEW_LAYER", "SCENES"}

_LAST_KEY: dict = {}
_TIMER_INTERVAL_FALLBACK = 0.15


def _interval() -> float:
    from . import properties

    prefs = properties.preferences()
    return prefs.interval if prefs else _TIMER_INTERVAL_FALLBACK


def invalidate() -> None:
    """Forget what was last seen, so the next tick acts even without a change."""
    _LAST_KEY.clear()


def _key(window):
    view_layer = window.view_layer
    if view_layer is None:
        return None
    active = view_layer.objects.active
    return (view_layer.name, active.as_pointer() if active else 0)


def _sync_area(window, area, collapse: bool) -> None:
    """Reveal the active object in one Outliner Area."""
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return
    with bpy.context.temp_override(window=window, area=area, region=region):
        if collapse:
            try:
                bpy.ops.outliner.show_one_level(open=False)
            except Exception:
                # A failed collapse must not cost us the reveal below.
                traceback.print_exc()
        bpy.ops.outliner.show_active()


def sync_window(window) -> None:
    """Run the recipe on every Outliner in one window, if the scene asks for it."""
    scene = window.scene
    screen = window.screen
    if scene is None or screen is None:
        return
    if not getattr(scene, "outliner_auto_highlight", False):
        return

    collapse = getattr(scene, "outliner_auto_highlight_collapse", False)
    for area in screen.areas:
        if area.type != 'OUTLINER':
            continue
        space = area.spaces.active
        if space is None or space.display_mode not in _TREE_MODES:
            continue
        try:
            _sync_area(window, area, collapse)
        except Exception:
            traceback.print_exc()


def sync_all() -> int:
    """Run the recipe everywhere, ignoring the change check. Returns the count."""
    done = 0
    for window in bpy.context.window_manager.windows:
        try:
            sync_window(window)
            done += 1
        except Exception:
            traceback.print_exc()
    return done


def _tick():
    """Timer body. Never raises: an exception here removes the timer for good."""
    try:
        windows = list(bpy.context.window_manager.windows)
        live = {w.as_pointer() for w in windows}
        for stale in [p for p in _LAST_KEY if p not in live]:
            del _LAST_KEY[stale]

        for window in windows:
            key = _key(window)
            if key is None:
                continue
            pointer = window.as_pointer()
            if _LAST_KEY.get(pointer) == key:
                continue
            _LAST_KEY[pointer] = key
            sync_window(window)
    except Exception:
        traceback.print_exc()
    return _interval()


def register() -> None:
    # Prime the cache: enabling the add-on should not yank the Outliner on the
    # first tick before the user has done anything.
    for window in bpy.context.window_manager.windows:
        key = _key(window)
        if key is not None:
            _LAST_KEY[window.as_pointer()] = key

    if not bpy.app.timers.is_registered(_tick):
        # persistent: the timer has to survive opening another file, otherwise
        # the whole thing silently stops working after a File > Open.
        bpy.app.timers.register(_tick, first_interval=_interval(), persistent=True)


def unregister() -> None:
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _LAST_KEY.clear()

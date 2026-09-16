"""Addon in die laufende Sitzung bringen und melden, was registriert ist.

Nutzt addon_utils.enable(..., persistent=False), damit der Test die
Blender-Preferences des Nutzers nicht dauerhaft veraendert.
"""

import inspect
import os
import sys
import traceback

import bpy
import addon_utils

PLUGIN_ROOT = r"C:\Users\conta\Dev\blender-tools\plugins\outliner-highlight"
MODULE = "outliner_highlight"


def log(text):
    print(text, flush=True)


try:
    log("enable-signatur: " + str(inspect.signature(addon_utils.enable)))
except Exception as exc:  # noqa: BLE001
    log(f"signatur n/a: {exc}")

# --- bereits aktivierte Addons, um die Hausnorm zu sehen ---
try:
    rows = []
    for mod in addon_utils.modules():
        try:
            enabled, _ = addon_utils.check(mod.__name__)
        except Exception:
            enabled = False
        if enabled:
            rows.append(mod.__name__)
    log(f"aktivierte Addons ({len(rows)}): {sorted(rows)}")
except Exception:
    log("Addon-Liste FAIL:\n" + traceback.format_exc())

# --- sys.path ---
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)
log(f"sys.path[0] = {sys.path[0]}")

# --- enable ---
try:
    addon_utils.enable(MODULE, default_set=False, persistent=False)
    log("enable: aufgerufen")
except Exception:
    log("enable FAIL:\n" + traceback.format_exc())

# --- was ist jetzt da? ---
try:
    enabled, _ = addon_utils.check(MODULE)
    log(f"check() -> enabled={enabled}")
except Exception as exc:  # noqa: BLE001
    log(f"check FAIL: {exc}")

try:
    prefs = bpy.context.preferences.addons[MODULE].preferences
    log(f"preferences: {type(prefs).__name__} | interval={prefs.interval} "
        f"header_button={prefs.header_button} enabled_on_startup={prefs.enabled_on_startup}")
except Exception as exc:  # noqa: BLE001
    log(f"preferences FEHLEN: {type(exc).__name__}: {exc}")

for prop in ("outliner_auto_highlight", "outliner_auto_highlight_collapse"):
    log(f"Scene.{prop} vorhanden: {hasattr(bpy.types.Scene, prop)}")

log(f"Operator sync registriert: {hasattr(bpy.ops.outliner, 'auto_highlight_sync')}")
log(f"Operator apply_all registriert: {hasattr(bpy.ops.outliner, 'auto_highlight_apply_all')}")

from outliner_highlight import watcher
log(f"Timer laeuft: {bpy.app.timers.is_registered(watcher._tick)}")
log(f"load_post handler drin: {any(getattr(h, '__name__', '') == '_load_post' for h in bpy.app.handlers.load_post)}")

log(f"Scene flag jetzt: {bpy.context.scene.outliner_auto_highlight} "
    f"collapse={bpy.context.scene.outliner_auto_highlight_collapse}")
log("INSTALL_OK")

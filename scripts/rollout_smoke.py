"""Ein echter Rollout-Zyklus, und was er hinterlaesst.

Der Reload ist die Stelle, an der dieses Addon am ehesten undicht wird: der
Watcher haelt seinen Timer als *Funktionsobjekt*, nicht unter einem Namen.
Wird das Modul aus ``sys.modules`` geworfen, ohne vorher ``unregister`` zu
rufen, meldet ``is_registered(neues_tick)`` False, ``register()`` legt einen
zweiten Timer an — und der alte laeuft weiter gegen tote Klassen.

Deshalb wird hier der alte Funktionszeiger festgehalten und nach dem Rollout
geprueft, ob er noch registriert ist. Ohne diese Referenz laesst sich ein
doppelter Timer von Python aus nicht nachweisen: ``bpy.app.timers`` hat keine
Methode, die registrierten Timer aufzulisten.
"""

import traceback

import bpy

ROLLOUT = r"C:\Users\conta\Dev\blender-tools\plugins\outliner-highlight\tools\rollout_addon.py"

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def draw_funcs(cls):
    draw = getattr(cls, "draw", None)
    return list(getattr(draw, "_draw_funcs", []))


# --- Zeiger auf die alte Generation ---
from outliner_highlight import ui as old_ui
from outliner_highlight import watcher as old_watcher

old_tick = old_watcher._tick
old_header = old_ui._draw_header
old_filter = old_ui._draw_filter
log(f"  alte Generation: tick={id(old_tick)} header={id(old_header)}")

# --- Rollout ---
try:
    exec(open(ROLLOUT, encoding="utf-8").read())
except Exception:
    log("  ROLLOUT FAIL:\n" + traceback.format_exc())

# --- neue Generation ---
from outliner_highlight import ui, watcher

log(f"  neue Generation: tick={id(watcher._tick)} header={id(ui._draw_header)}")
log(f"  alter Timer noch registriert: {bpy.app.timers.is_registered(old_tick)}")
log(f"  neuer Timer registriert:      {bpy.app.timers.is_registered(watcher._tick)}")

header_funcs = draw_funcs(bpy.types.OUTLINER_HT_header)
filter_funcs = draw_funcs(bpy.types.OUTLINER_PT_filter)
log(f"  Header-draws: {len(header_funcs)} | alt drin: {old_header in header_funcs} "
    f"| neu drin: {ui._draw_header in header_funcs}")
log(f"  Filter-draws: {len(filter_funcs)} | alt drin: {old_filter in filter_funcs} "
    f"| neu drin: {ui._draw_filter in filter_funcs}")

# --- laeuft es noch? Aktives Objekt in eine flache Collection setzen ---
scene = bpy.context.scene
target = None
for coll_name in ("scatter objects", "surfaces"):
    coll = bpy.data.collections.get(coll_name)
    if coll and len(coll.objects):
        target = coll.objects[0]
        break

if target is None:
    log("  kein Testobjekt gefunden")
else:
    for other in list(bpy.data.objects):
        try:
            other.select_set(False)
        except Exception:
            pass
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    watcher.invalidate()
    log(f"  aktives Objekt = {target.name} (Collection flach) | "
        f"on={scene.outliner_auto_highlight} collapse={scene.outliner_auto_highlight_collapse}")

log("SMOKE_DONE")

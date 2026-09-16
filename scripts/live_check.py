"""Ende-zu-Ende-Pruefung des Addons in der laufenden Sitzung.

Der Beweis, der zaehlt, ist der Timer-Pfad: Auswahl aendern, Skript verlassen,
Moment warten, dann einen Screenshot machen. Ein direkter Operator-Aufruf wuerde
nur zeigen, dass die Operatoren funktionieren, nicht dass das Addon sie von
selbst ausloest.

Aufruf mit Schritt:
    STEP = "setup"; exec(open(PFAD).read())
Schritte: setup | active | shot:<tag>
"""

import os

import bpy
import numpy as np

OUT = "C:/Users/conta/AppData/Local/Temp/ah_test"
PREFIX = "AHLIVE_"
STEP = globals().get("STEP", "setup")
os.makedirs(OUT, exist_ok=True)


def log(text):
    print(text, flush=True)


# ---------------------------------------------------------------- helpers

def _area():
    win = bpy.context.window_manager.windows[0]
    outs = [a for a in win.screen.areas if a.type == 'OUTLINER']
    big = max(outs, key=lambda a: a.height)
    return win, big, (big.x, big.y, big.width, big.height)


def shot(tag):
    win, area, box = _area()
    raw = f"{OUT}/{tag}_full.png"
    bpy.ops.screen.screenshot(filepath=raw)
    img = bpy.data.images.load(raw)
    width, height = img.size
    buf = np.empty(width * height * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    flat = buf.reshape(height, width, 4)
    x, y, w, h = box
    sub = flat[max(0, y):min(height, y + h), max(0, x):min(width, x + w)]
    out = bpy.data.images.new("crop", width=sub.shape[1], height=sub.shape[0], alpha=True)
    out.pixels.foreach_set(sub.reshape(-1).copy())
    out.filepath_raw = f"{OUT}/{tag}.png"
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    bpy.data.images.remove(img)
    log(f"  screenshot: {tag}.png")


def cleanup():
    for name in [o.name for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    for name in [c.name for c in bpy.data.collections if c.name.startswith(PREFIX)]:
        coll = bpy.data.collections.get(name)
        if coll:
            bpy.data.collections.remove(coll)
    for name in [m.name for m in bpy.data.meshes if m.name.startswith(PREFIX)]:
        mesh = bpy.data.meshes.get(name)
        if mesh:
            bpy.data.meshes.remove(mesh)
    bpy.context.view_layer.update()


def build():
    scene = bpy.context.scene
    root = bpy.data.collections.new(PREFIX + "Root")
    scene.collection.children.link(root)

    made = {}
    parent = root
    for tag in ("A", "B", "C"):
        coll = bpy.data.collections.new(PREFIX + tag)
        parent.children.link(coll)
        parent = coll
        mesh = bpy.data.meshes.new(PREFIX + tag + "_mesh")
        obj = bpy.data.objects.new(PREFIX + tag + "_obj", mesh)
        coll.objects.link(obj)
        made[tag] = obj

    for tag in ("Other", "Sib1", "Sib2"):
        coll = bpy.data.collections.new(PREFIX + tag)
        scene.collection.children.link(coll)
        mesh = bpy.data.meshes.new(PREFIX + tag + "_mesh")
        obj = bpy.data.objects.new(PREFIX + tag + "_obj", mesh)
        coll.objects.link(obj)
        made[tag] = obj

    bpy.context.view_layer.update()
    return made


def set_active(obj):
    for other in list(bpy.data.objects):
        try:
            other.select_set(False)
        except Exception:
            pass
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ---------------------------------------------------------------- steps

def step_setup():
    from outliner_highlight import watcher

    cleanup()
    made = build()
    scene = bpy.context.scene
    scene.outliner_auto_highlight = True
    scene.outliner_auto_highlight_collapse = True
    log(f"  flags: on={scene.outliner_auto_highlight} collapse={scene.outliner_auto_highlight_collapse}")

    # Aktives Objekt bewusst in eine flache Collection: nach dem naechsten Tick
    # muss der Baum zu sein und nur diese eine Collection offen.
    flat = made["Sib1"]
    set_active(flat)
    watcher.invalidate()
    log(f"  aktives Objekt = {flat.name} (flache Collection)")
    log("  -> Skript verlassen, Timer laufen lassen, dann STEP='shot:40_flat'")


def step_active():
    from outliner_highlight import watcher

    obj = bpy.data.objects.get(globals().get("TARGET", PREFIX + "C_obj"))
    if obj is None:
        log(f"  FEHLER: Ziel nicht gefunden: {globals().get('TARGET')}")
        return
    set_active(obj)
    watcher.invalidate()
    log(f"  aktives Objekt = {obj.name}")
    log("  -> Skript verlassen, Timer laufen lassen, dann Screenshot")


log(f"STEP={STEP}")
if STEP == "setup":
    step_setup()
elif STEP == "active":
    step_active()
elif STEP.startswith("shot:"):
    shot(STEP.split(":", 1)[1])
else:
    log("unbekannter Schritt")
log("STEP_DONE")

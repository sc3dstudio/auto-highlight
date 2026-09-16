"""Den Screenshot fuer Preview 2 aufnehmen: ein sauberer, tief verschachtelter Baum.

Laeuft in Blender:  exec(open(PFAD).read())

Warum ein eigener Baum und nicht der Test-Fixture aus ``41_deep.png``: dort hiessen
die Collections ``AHLIVE_A``, ``AHLIVE_B``, ``AHLIVE_C``. Fuer eine
Marktplatz-Vorschau liest sich das wie Geruest, nicht wie eine Szene. Die
Verschachtelung ist derselbe Punkt, nur mit Namen, die man zeigen kann.

Schreibt ``assets/nested.png`` (nur der Outliner-Bereich, ungeschnitten) — die
Zuschnittwahl fuer die Vorschau passiert in ``tools/make_assets.py``, damit sie
dort nachvollziehbar steht und nicht hier versteckt ist.

Raeumt die angelegten Collections am Ende wieder weg und stellt die Flags her.
"""

import os
import traceback

import numpy as np

import bpy

REPO = r"C:\Users\conta\Dev\blender-tools\plugins\outliner-highlight"
OUT = os.path.join(REPO, "assets", "nested.png")

# Environment > City > Buildings > Marina, jeweils mit einem Objekt, damit die
# Kette nicht nur aus leeren Collections besteht.
CHAIN = ("Environment", "City", "Buildings", "Marina")
SIBLINGS = ("Terrain", "Props")

# Aufgeraeumt wird ueber gemerkte Referenzen, nicht ueber einen Namenspraefix:
# ein Praefix in den Collection-Namen waere im Screenshot zu lesen, und der geht
# auf einen Marktplatz. Ohne Praefix muss die Liste exakt sein — ein
# praefixbasierter Aufraeumer koennte hier sonst nichts finden.
_MADE = []

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def outliner_area():
    win = bpy.context.window_manager.windows[0]
    area = max([a for a in win.screen.areas if a.type == 'OUTLINER'], key=lambda a: a.height)
    return win, area


def make_mesh_object(name):
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    _MADE.extend((mesh, obj))
    return obj


def build():
    scene = bpy.context.scene
    made = []
    parent = scene.collection
    for name in CHAIN:
        coll = bpy.data.collections.new(name)
        _MADE.append(coll)
        parent.children.link(coll)
        parent = coll
        obj = make_mesh_object(name + "_Block")
        coll.objects.link(obj)
        made.append(obj)
    for name in SIBLINGS:
        coll = bpy.data.collections.new(name)
        _MADE.append(coll)
        scene.collection.children.link(coll)
        obj = make_mesh_object(name + "_Patch")
        coll.objects.link(obj)
        made.append(obj)
    bpy.context.view_layer.update()
    return made


def cleanup():
    if not _MADE:
        return
    try:
        bpy.data.batch_remove([item for item in _MADE if item is not None])
    except Exception:
        traceback.print_exc()
    _MADE.clear()
    bpy.context.view_layer.update()


def capture():
    from outliner_highlight import watcher

    cleanup()
    made = build()
    deep = made[len(CHAIN) - 1]  # Marina_Block, drei Ebenen tief

    for other in list(bpy.data.objects):
        try:
            other.select_set(False)
        except Exception:
            pass
    deep.select_set(True)
    bpy.context.view_layer.objects.active = deep
    log(f"  aktives Objekt: {deep.name}")

    # Der Baum wird ohnehin von der Erweiterung aufgeraeumt; der Aufruf stellt
    # sicher, dass der Screenshot den Zustand zeigt und nicht einen Zufall.
    watcher.invalidate()
    watcher.sync_all()
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)

    _, area = outliner_area()
    raw = os.path.join(os.path.dirname(OUT), "_nested_full.png")
    bpy.ops.screen.screenshot(filepath=raw)

    img = bpy.data.images.load(raw)
    width, height = img.size
    buf = np.empty(width * height * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    flat = buf.reshape(height, width, 4)
    x, y, w, h = area.x, area.y, area.width, area.height
    sub = flat[max(0, y):min(height, y + h), max(0, x):min(width, x + w)]
    out = bpy.data.images.new("crop", width=sub.shape[1], height=sub.shape[0], alpha=True)
    out.pixels.foreach_set(sub.reshape(-1).copy())
    out.filepath_raw = OUT
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    bpy.data.images.remove(img)
    os.remove(raw)
    log(f"  geschrieben: {OUT} ({sub.shape[1]}x{sub.shape[0]})")

    return deep


try:
    capture()
    cleanup()
    log("  Demo wieder entfernt")
    log("CAPTURE_OK")
except Exception:
    log("FAIL:\n" + traceback.format_exc())
    cleanup()

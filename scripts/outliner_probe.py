"""Probe: was machen die Outliner-Operatoren in dieser Blender-Version wirklich?

Laeuft im offenen Blender. Baut eine temporaere Collection-Struktur, setzt ein
tief verschachteltes Objekt aktiv und macht nach jedem Operator einen Screenshot,
damit man den aufgeklappten Zustand visuell vergleichen kann.

Aufruf:  exec(open(PFAD).read())
Aufraeumen passiert am Ende automatisch.
"""

import os
import numpy as np
import bpy

OUT = "C:/Users/conta/AppData/Local/Temp/ah_test"
PREFIX = "AHPROBE_"
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------- screenshot

def _crop_save(src, box, dst):
    img = bpy.data.images.load(src)
    width, height = img.size
    buf = np.empty(width * height * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    flat = buf.reshape(height, width, 4)
    x, y, w, h = box
    y0, y1 = max(0, min(y, height)), max(0, min(y + h, height))
    x0, x1 = max(0, min(x, width)), max(0, min(x + w, width))
    sub = flat[y0:y1, x0:x1]
    out = bpy.data.images.new("crop", width=sub.shape[1], height=sub.shape[0], alpha=True)
    out.pixels.foreach_set(sub.reshape(-1).copy())
    out.filepath_raw = dst
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    bpy.data.images.remove(img)


def _area():
    win = bpy.context.window_manager.windows[0]
    outs = [a for a in win.screen.areas if a.type == 'OUTLINER']
    big = max(outs, key=lambda a: a.height)
    return win, big, (big.x, big.y, big.width, big.height)


def shot(tag):
    win, area, box = _area()
    raw = f"{OUT}/{tag}_full.png"
    bpy.ops.screen.screenshot(filepath=raw)
    _crop_save(raw, box, f"{OUT}/{tag}.png")
    return tag


def op(label, fn, **kw):
    win, area, box = _area()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region):
        try:
            res = fn(**kw)
            print(f"    {label:34s} -> {res}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {label:34s} !! {type(exc).__name__}: {exc}")
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)


# ---------------------------------------------------------------- cleanup

def cleanup():
    for name in [c.name for c in bpy.data.collections if c.name.startswith(PREFIX)]:
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        for obj_name in [o.name for o in coll.objects if o]:
            obj = bpy.data.objects.get(obj_name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)
    for name in [m.name for m in bpy.data.meshes if m.name.startswith(PREFIX)]:
        mesh = bpy.data.meshes.get(name)
        if mesh:
            bpy.data.meshes.remove(mesh)
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- setup

def build():
    scene = bpy.context.scene
    root = bpy.data.collections.new(PREFIX + "Root")
    scene.collection.children.link(root)

    objs = []
    parent = root
    for tag in ("A", "B", "C"):
        coll = bpy.data.collections.new(PREFIX + tag)
        parent.children.link(coll)
        parent = coll
        mesh = bpy.data.meshes.new(PREFIX + tag + "_mesh")
        obj = bpy.data.objects.new(PREFIX + tag + "_obj", mesh)
        coll.objects.link(obj)
        objs.append(obj)

    for tag in ("Sib1", "Sib2"):
        coll = bpy.data.collections.new(PREFIX + tag)
        scene.collection.children.link(coll)
        mesh = bpy.data.meshes.new(PREFIX + tag + "_mesh")
        obj = bpy.data.objects.new(PREFIX + tag + "_obj", mesh)
        coll.objects.link(obj)
        objs.append(obj)

    bpy.context.view_layer.update()
    return objs


def set_active(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ---------------------------------------------------------------- run

def main():
    cleanup()
    objs = build()
    deep = objs[2]

    win, area, box = _area()
    space = area.spaces.active
    print(f"  Outliner {area.width}x{area.height} display_mode={space.display_mode} "
          f"scroll_to_active={space.scroll_to_active}")

    set_active(deep)
    print(f"  active = {deep.name}")
    shot("20_baseline")

    print("  -- collapse --")
    op("show_one_level(open=False)", bpy.ops.outliner.show_one_level, open=False)
    shot("21_one_level_false")

    print("  -- expand one level (back) --")
    op("show_one_level(open=True)", bpy.ops.outliner.show_one_level, open=True)
    shot("22_one_level_true")

    print("  -- collapse again, deeper tree should need 1 call? --")
    op("show_one_level(open=False) #2", bpy.ops.outliner.show_one_level, open=False)
    shot("23_one_level_false2")

    print("  -- item_openclose(all=True) --")
    op("item_openclose(all=True)", bpy.ops.outliner.item_openclose, all=True)
    shot("24_item_openclose_all")

    print("  -- show_active --")
    op("show_active", bpy.ops.outliner.show_active)
    shot("25_show_active")

    print("  -- collapse then show_active (the real recipe) --")
    op("show_one_level(open=False) #3", bpy.ops.outliner.show_one_level, open=False)
    op("show_active #2", bpy.ops.outliner.show_active)
    shot("26_collapse_then_show_active")

    return "probe done"


result = main()
print(result)

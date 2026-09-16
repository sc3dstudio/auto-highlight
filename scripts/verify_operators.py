"""Beide Operatoren wirklich aufrufen, nicht nur ihre Existenz pruefen.

Laeuft in Blender:  exec(open(PFAD).read())

Die uebrigen Pruefungen schauen nach, ob die Operatoren *registriert* sind. Das
ist eine andere Aussage als "sie tun etwas": ein Tippfehler im execute-Rumpf
oder ein Poll, der nie wahr wird, bliebe dabei unsichtbar. Hier wird deshalb
jeder Operator einmal ausgeloest und seine Wirkung nachgemessen.

``auto_highlight_sync`` pollt auf ``context.area.type == 'OUTLINER'``, laeuft
also nur mit passendem Override. Ohne wuerde der Aufruf still 'CANCELLED'
liefern — und genau deshalb wird das Ergebnis geprueft und nicht angenommen.

Verwendet nur Objekte, die schon in der Szene sind: Testkram anzulegen und
wieder wegzuraeumen hat in dieser Sitzung schon einmal einen Aufraeumfehler
gekostet, den es hier nicht braucht.
"""

import traceback

import bpy

from outliner_highlight import watcher

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def area_and_region():
    win = bpy.context.window_manager.windows[0]
    area = max([a for a in win.screen.areas if a.type == 'OUTLINER'], key=lambda a: a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return win, area, region


def main():
    win, area, region = area_and_region()
    scene = bpy.context.scene

    # ---- 1) apply_all: Flags vorher aus, danach an ----
    for sc in bpy.data.scenes:
        sc.outliner_auto_highlight = False
        sc.outliner_auto_highlight_collapse = False
    log(f"  vor apply_all: {[s.outliner_auto_highlight for s in bpy.data.scenes]}")

    result = bpy.ops.outliner.auto_highlight_apply_all()
    log(f"  apply_all -> {result}")
    assert result == {'FINISHED'}, f"apply_all: {result}"
    assert all(s.outliner_auto_highlight for s in bpy.data.scenes), "Flag nicht gesetzt"
    log(f"  nach apply_all: {[s.outliner_auto_highlight for s in bpy.data.scenes]}")

    # Der Sync-Operator soll hier sichtbar arbeiten.
    scene.outliner_auto_highlight_collapse = True

    # ---- 2) sync: Baum zuwerfen, dann ohne Auswahlwechsel aufrufen ----
    obj = bpy.data.objects.get("Lamborghini Revuelto super car")
    assert obj is not None, "Testobjekt fehlt"
    for other in list(bpy.data.objects):
        try:
            other.select_set(False)
        except Exception:
            pass
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    log(f"  aktives Objekt: {bpy.context.view_layer.objects.active.name}")

    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.outliner.show_one_level(open=False)
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
    shot("60_before_sync")

    # Ohne Auswahlwechsel: der Timer wuerde hier nichts tun, weil der Schluessel
    # gleich bleibt. Genau dafuer ist der Operator da.
    with bpy.context.temp_override(window=win, area=area, region=region):
        result = bpy.ops.outliner.auto_highlight_sync()
    log(f"  auto_highlight_sync -> {result}")
    assert result == {'FINISHED'}, f"sync: {result}"

    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
    shot("61_after_sync")
    log("  -> Screenshot 61 muss die Collection des aktiven Objekts offen zeigen")
    return "OPERATOR_CHECK_OK"


def shot(tag):
    import os

    import numpy as np

    out = "C:/Users/conta/AppData/Local/Temp/ah_test"
    os.makedirs(out, exist_ok=True)
    _, area, _ = area_and_region()
    raw = f"{out}/{tag}_full.png"
    bpy.ops.screen.screenshot(filepath=raw)

    img = bpy.data.images.load(raw)
    width, height = img.size
    buf = np.empty(width * height * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    flat = buf.reshape(height, width, 4)
    x, y, w, h = area.x, area.y, area.width, area.height
    sub = flat[max(0, y):min(height, y + h), max(0, x):min(width, x + w)]
    out_img = bpy.data.images.new("crop", width=sub.shape[1], height=sub.shape[0], alpha=True)
    out_img.pixels.foreach_set(sub.reshape(-1).copy())
    out_img.filepath_raw = f"{out}/{tag}.png"
    out_img.file_format = 'PNG'
    out_img.save()
    bpy.data.images.remove(out_img)
    bpy.data.images.remove(img)
    log(f"  screenshot: {tag}.png")


try:
    log(main())
except AssertionError as exc:
    log(f"FAIL: {exc}")
except Exception:
    log("FAIL:\n" + traceback.format_exc())

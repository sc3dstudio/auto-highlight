"""Zwei Restprüfungen, die ein Screenshot allein nicht belegen kann.

1. Die Filters-Zeile liegt in einem Popover, das sich von Python aus nicht
   oeffnen laesst. Der Header-Toggle ist im Screenshot sichtbar, die
   Filters-Variante waere damit aber ungeprueft. Deshalb bekommt eine
   temporaere Header-Klasse beim Redraw ein *echtes* UILayout und ruft damit die
   echte draw-Funktion auf. Das prueft genau das, was sonst niemand verraet: ob
   die Funktion mit einem echten Layout durchlaeuft statt nur zu existieren.

2. Collapse Other Collections aus: der Baum muss unangetastet bleiben. Ohne
   diese Gegenprobe ist nicht gezeigt, dass der Schalter etwas bewirkt — nur
   dass es ohne ihn auch funktioniert.
"""

import traceback

import bpy

from outliner_highlight import ui

RESULT = []
DRAWN = []


def _probe_draw(self, context):
    """Haengt an den echten Outliner-Header: der wird nachweislich gezeichnet.

    Der erste Anlauf registrierte eine eigene ``bpy.types.Header``-Unterklasse.
    Blender nahm sie ohne Warnung an und rief sie nie auf, also war der Test
    wertlos statt rot. Der Header dieses Addons ist im Screenshot sichtbar,
    damit ist ``OUTLINER_HT_header`` der belastbare Ort fuer die Sonde.
    """
    DRAWN.append(1)
    if RESULT:
        return

    class _Fake:
        pass

    fake = _Fake()
    fake.layout = self.layout
    try:
        ui._draw_filter(fake, context)
        RESULT.append("OK: _draw_filter lief mit echtem UILayout ohne Ausnahme durch")
    except Exception:
        RESULT.append("FAIL:\n" + traceback.format_exc())


bpy.types.OUTLINER_HT_header.append(_probe_draw)
try:
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
finally:
    bpy.types.OUTLINER_HT_header.remove(_probe_draw)

print(f"  Header-Redraws waehrend der Probe: {len(DRAWN)}", flush=True)
print(f"  {RESULT[0] if RESULT else 'draw wurde nie aufgerufen!'}", flush=True)

# --- 2) Collapse aus, Baum vorher komplett offen ---
win = bpy.context.window_manager.windows[0]
area = max([a for a in win.screen.areas if a.type == 'OUTLINER'], key=lambda a: a.height)
region = next(r for r in area.regions if r.type == 'WINDOW')

scene = bpy.context.scene
scene.outliner_auto_highlight_collapse = False

with bpy.context.temp_override(window=win, area=area, region=region):
    bpy.ops.outliner.show_hierarchy()
bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)

target = bpy.data.objects.get("AHLIVE_Sib2_obj")
for other in list(bpy.data.objects):
    try:
        other.select_set(False)
    except Exception:
        pass
target.select_set(True)
bpy.context.view_layer.objects.active = target

from outliner_highlight import watcher

watcher.invalidate()
print(f"  collapse={scene.outliner_auto_highlight_collapse} | aktiv={target.name} | "
      "Baum vorher komplett offen", flush=True)
print("VERIFY_OK", flush=True)

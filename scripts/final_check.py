"""Abschlusspruefung und Aufraeumen in einem Durchgang.

Drei Dinge, die ein Screenshot nicht zeigt:

1. **Kein Leck in den UI-Hooks.** ``Panel.append`` / ``Header.append`` haengen
   eine Funktion an eine Liste auf der Klasse. Ein unregister, das sie nicht
   wieder entfernt, laesst sie dort stehen — und nach ein paar Addon-Reloads
   zeichnet Blender denselben Knopf mehrfach. Deshalb wird die draw-Liste vor
   und nach einem unregister/register-Zyklus verglichen.
2. **Die Preferences-Definitionen sind gueltig.** Ohne die Felder in der RNA
   faellt ``_interval()`` still auf den Ersatzwert zurueck.
3. **Die Sitzung ist so sauber wie vorher.** Testobjekte raus, und
   ``scroll_to_active`` zurueck auf den Wert, den die Outliner vorher hatten.

Warum jeder Schritt in einem eigenen try steht: Blender verwirft die komplette
Ausgabe eines Skripts, sobald es eine Ausnahme gibt. Ohne diese Klammern sieht
man bei einem Fehler in Schritt 3 nicht, was Schritt 1 und 2 ergeben haben.

Warum ``batch_remove`` statt einer Schleife: ``bpy.data.objects.remove()`` in
einer Schleife laesst tote Zeiger in den Listen stehen, die der naechste
Zugriff auf ``bpy.data.objects`` als "StructRNA of type Object has been removed"
quittiert. Genau daran sind zwei Anlaeufe dieses Skripts gescheitert.
"""

import traceback

import bpy

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def step(label, fn):
    try:
        fn()
    except Exception:
        log(f"  {label} FAIL:\n{traceback.format_exc()}")


def draw_funcs(cls):
    draw = getattr(cls, "draw", None)
    return list(getattr(draw, "_draw_funcs", []))


# ---------------------------------------------------------------- 1) Hooks
def check_hooks():
    from outliner_highlight import ui

    for label, cls, func in (("header", bpy.types.OUTLINER_HT_header, ui._draw_header),
                             ("filter", bpy.types.OUTLINER_PT_filter, ui._draw_filter)):
        before = len(draw_funcs(cls))
        ui.unregister()
        during = len(draw_funcs(cls))
        ui.register()
        after = len(draw_funcs(cls))
        log(f"  {label}: draw-Liste {before} -> nach unregister {during} -> "
            f"nach register {after} | unsere Funktion drin: {func in draw_funcs(cls)}")


# ---------------------------------------------------------------- 2) Prefs
def check_prefs():
    from outliner_highlight import properties

    ids = sorted(p.identifier
                 for p in properties.OutlinerHighlightPreferences.bl_rna.properties
                 if p.identifier != "rna_type")
    log(f"  Preferences-Felder: {ids}")
    log(f"  preferences() ohne aktiviertes Addon: {properties.preferences()}")


# ---------------------------------------------------------------- 3) Aufraeumen
def cleanup():
    prefix = "AHLIVE_"
    doomed = [o for o in bpy.data.objects if o.name.startswith(prefix)]
    doomed += [c for c in bpy.data.collections if c.name.startswith(prefix)]
    doomed += [m for m in bpy.data.meshes if m.name.startswith(prefix)]
    log(f"  zu entfernen: {len(doomed)} Datablocks")
    if doomed:
        bpy.data.batch_remove(doomed)
    log(f"  Collections jetzt: {[c.name for c in bpy.context.scene.collection.children]}")
    log(f"  Testobjekte uebrig: {[o.name for o in bpy.data.objects if o.name.startswith(prefix)]}")


# ---------------------------------------------------------------- 4) scroll_to_active
def restore_scroll():
    win = bpy.context.window_manager.windows[0]
    for area in win.screen.areas:
        if area.type == 'OUTLINER':
            area.spaces.active.scroll_to_active = True
    log("  scroll_to_active zurueckgesetzt: "
        f"{[a.spaces.active.scroll_to_active for a in win.screen.areas if a.type == 'OUTLINER']}")


# ---------------------------------------------------------------- 5) Endzustand
def final_state():
    from outliner_highlight import watcher

    scene = bpy.context.scene
    scene.outliner_auto_highlight = True
    scene.outliner_auto_highlight_collapse = True
    watcher.invalidate()
    log(f"  Endzustand: on={scene.outliner_auto_highlight} "
        f"collapse={scene.outliner_auto_highlight_collapse} | "
        f"Timer={bpy.app.timers.is_registered(watcher._tick)}")


step("1 Hooks", check_hooks)
step("2 Prefs", check_prefs)
step("3 Cleanup", cleanup)
step("4 scroll_to_active", restore_scroll)
step("5 Endzustand", final_state)
log("FINAL_DONE")

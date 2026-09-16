"""Den gebauten Release-Zip wie eine Installation behandeln und pruefen.

Laeuft in Blender:  exec(open(PFAD).read())

Was hier nachgestellt wird, ist genau das, was Blenders *Install from Disk*
tut: Archiv in einen Ordner entpacken, diesen Ordner auf ``sys.path`` setzen,
``outliner_highlight`` importieren, ``register()`` rufen. Blender kopiert dabei
zusaetzlich nach ``scripts/addons/`` — fuer den Import ist das der einzige
Unterschied, und dieser Test soll die Blender-Konfiguration des Nutzers nicht
anfassen.

Die entscheidende Zusicherung ist, dass wirklich das Archiv getestet wird und
nicht der Arbeitsstand daneben: beide heissen ``outliner_highlight``, und der
Rollout hat den Plugin-Ordner bereits auf ``sys.path`` gelegt. Deshalb wird
dieser Pfad entfernt, das Extraktionsverzeichnis nach vorne gesetzt und danach
``__file__`` geprueft. Ohne diese Kontrolle waere ein gruener Test wertlos.

Am Ende wird der Arbeitsstand wieder registriert, damit die Sitzung so
zurueckbleibt, wie sie war.
"""

import hashlib
import os
import shutil
import sys
import tempfile
import traceback
import zipfile

import bpy

REPO = r"C:\Users\conta\Dev\blender-tools\plugins\outliner-highlight"
PACKAGE = "outliner_highlight"
ARCHIVE = os.path.join(REPO, "dist", "outliner-highlight-0.1.0.zip")
WORK_ROOT = REPO

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def verified():
    """Die Zusicherungen. Erste Ausnahme beendet, deshalb in Reihenfolge."""
    global ARCHIVE
    if not os.path.isfile(ARCHIVE):
        raise SystemExit(f"Archiv fehlt: {ARCHIVE}")

    # --- 1) Inhalt des Archivs ---
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
    log(f"  Archiv: {os.path.basename(ARCHIVE)} | {len(names)} Dateien")
    assert f"{PACKAGE}/__init__.py" in names, "Package liegt nicht auf Archivwurzel"
    assert not any("__pycache__" in n for n in names), "__pycache__ im Archiv"
    assert not any(n.endswith((".pyc", ".pyo")) for n in names), ".pyc im Archiv"
    for name in sorted(names):
        log(f"    {name}")

    # --- 2) Entpacken wie eine Installation ---
    tmp = tempfile.mkdtemp(prefix="ah_zip_verify_")
    with zipfile.ZipFile(ARCHIVE) as zf:
        zf.extractall(tmp)

    # --- 3) Dafür sorgen, dass der Import wirklich aus tmp kommt ---
    # Arbeitsstand stilllegen: aus sys.modules werfen und abmelden.
    stale = sys.modules.get(PACKAGE)
    if stale is not None and hasattr(stale, "unregister"):
        stale.unregister()
    for entry in [m for m in list(sys.modules)
                  if m == PACKAGE or m.startswith(PACKAGE + ".")]:
        del sys.modules[entry]

    # Der Rollout hat den Plugin-Ordner auf sys.path gelegt; beide Module heissen
    # gleich, also muss er weg, sonst importiert der Test den Arbeitsstand.
    removed = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) ==
               os.path.normcase(WORK_ROOT)]
    for path in removed:
        sys.path.remove(path)
    sys.path.insert(0, tmp)
    log(f"  sys.path: {len(removed)} Arbeitsstand-Pfad(e) entfernt, tmp vorne")

    import importlib
    importlib.invalidate_caches()
    module = importlib.import_module(PACKAGE)

    origin = os.path.normcase(os.path.abspath(module.__file__))
    assert origin.startswith(os.path.normcase(os.path.abspath(tmp))), (
        f"getestet wird nicht das Archiv: {module.__file__}"
    )
    log(f"  importiert aus: {module.__file__}")
    log(f"  bl_info: {module.bl_info['name']} {module.bl_info['version']}")

    # --- 4) Registrieren ---
    module.register()

    from outliner_highlight import ui, watcher
    assert hasattr(bpy.types.Scene, "outliner_auto_highlight"), "Scene-Property fehlt"
    assert hasattr(bpy.types.Scene, "outliner_auto_highlight_collapse"), \
        "Collapse-Property fehlt"
    assert hasattr(bpy.ops.outliner, "auto_highlight_sync"), "Sync-Operator fehlt"
    assert hasattr(bpy.ops.outliner, "auto_highlight_apply_all"), "Apply-Operator fehlt"
    assert bpy.app.timers.is_registered(watcher._tick), "Timer laeuft nicht"

    def draw_funcs(cls):
        draw = getattr(cls, "draw", None)
        return list(getattr(draw, "_draw_funcs", []))

    assert ui._draw_header in draw_funcs(bpy.types.OUTLINER_HT_header), \
        "Header-Hook fehlt"
    assert ui._draw_filter in draw_funcs(bpy.types.OUTLINER_PT_filter), \
        "Filter-Hook fehlt"
    log("  registriert: 2 Scene-Properties, 2 Operatoren, Timer, 2 UI-Hooks")

    # --- 5) Sauber abmelden ---
    module.unregister()
    assert not bpy.app.timers.is_registered(watcher._tick), "Timer ueberlebt unregister"
    assert ui._draw_header not in draw_funcs(bpy.types.OUTLINER_HT_header), \
        "Header-Hook ueberlebt unregister"
    log("  unregister: Timer und UI-Hooks wieder weg")

    # --- 6) Arbeitsstand zurueck in die Sitzung ---
    for entry in [m for m in list(sys.modules)
                  if m == PACKAGE or m.startswith(PACKAGE + ".")]:
        del sys.modules[entry]
    sys.path.remove(tmp)
    if WORK_ROOT not in sys.path:
        sys.path.insert(0, WORK_ROOT)
    importlib.invalidate_caches()
    from outliner_highlight import watcher as live_watcher

    sys.modules[PACKAGE].register()
    assert bpy.app.timers.is_registered(live_watcher._tick), "Arbeitsstand nicht registriert"
    log("  Arbeitsstand wieder registriert")

    shutil.rmtree(tmp, ignore_errors=True)
    return "ZIP_VERIFY_OK"


try:
    log(verified())
except AssertionError as exc:
    log(f"FAIL: {exc}")
except Exception:
    log("FAIL:\n" + traceback.format_exc())

"""Beide Release-Archive wie eine Installation behandeln und pruefen.

Laeuft in Blender:  exec(open(PFAD).read())

Was hier nachgestellt wird, ist das, was Blender beim Installieren tut: Archiv
entpacken, das Package auf ``sys.path`` legen, importieren, ``register()`` rufen.
Blender kopiert dabei zusaetzlich in seinen Addon- bzw. Extension-Ordner — fuer
den Import ist das der einzige Unterschied, und dieser Test soll die
Blender-Konfiguration des Nutzers nicht anfassen.

Die beiden Archive haben unterschiedliche Wurzen, und genau das ist der Punkt,
an dem eine Installation still scheitert:

* **legacy** — das Archiv enthaelt den Ordner ``outliner_highlight/``. Er wird
  entpackt, das Entpackungsverzeichnis kommt auf ``sys.path``.
* **extension** — das Archiv *ist* das Package: ``__init__.py`` und
  ``blender_manifest.toml`` liegen auf der Wurzel, ohne Ordner. Blender legt es
  als ``<extensions>/<repo>/outliner_highlight/`` ab; hier wird das
  nachgestellt, indem die Wurzel nach ``tmp/outliner_highlight/`` entpackt wird
  und ``tmp`` auf ``sys.path`` kommt.

Die entscheidende Zusicherung ist, dass wirklich das Archiv getestet wird und
nicht der Arbeitsstand daneben: beide heissen ``outliner_highlight``. Deshalb
wird der Plugin-Ordner aus ``sys.path`` entfernt, das Entpackungsverzeichnis nach
vorne gesetzt und danach ``__file__`` geprueft. Ohne diese Kontrolle waere ein
gruener Test wertlos.

Das Format selbst prueft Blender besser als dieses Skript::

    blender --command extension validate <extension-zip>
"""

import glob
import importlib
import os
import shutil
import sys
import tempfile
import traceback
import zipfile

import bpy

REPO = r"C:\Users\conta\Dev\blender-tools\plugins\outliner-highlight"
PACKAGE = "outliner_highlight"
DIST = os.path.join(REPO, "dist")


def archives():
    """Beide Archive aus dist/ finden, ohne den Versionsstand zu wiederholen.

    Eine fest eingetragene Version hier waere bei jedem Release falsch, und zwar
    still: das Skript wuerde die *alte* Zip pruefen und gruen melden.
    """
    found = []
    for path in sorted(glob.glob(os.path.join(DIST, "outliner-highlight-*.zip"))):
        is_legacy = path.endswith("-legacy.zip")
        found.append(("legacy" if is_legacy else "extension",
                      os.path.relpath(path, REPO), not is_legacy))
    kinds = {label for label, _path, _rooted in found}
    assert kinds == {"extension", "legacy"}, f"nicht beide Archive gefunden: {kinds}"
    return found

lines = []


def log(text):
    lines.append(text)
    print(text, flush=True)


def draw_funcs(cls):
    draw = getattr(cls, "draw", None)
    return list(getattr(draw, "_draw_funcs", []))


def unload_package():
    """Arbeitsstand aus sys.modules werfen, vorher abmelden."""
    stale = sys.modules.get(PACKAGE)
    if stale is not None and hasattr(stale, "unregister"):
        stale.unregister()
    for entry in [m for m in list(sys.modules)
                  if m == PACKAGE or m.startswith(PACKAGE + ".")]:
        del sys.modules[entry]


def isolate_from_workcopy():
    """Den Arbeitsstand-Pfad aus sys.path entfernen.

    Der Rollout hat den Plugin-Ordner dort abgelegt; das Modul heisst gleich, also
    muss er weg, sonst importiert der Test den Arbeitsstand statt das Archiv.
    """
    removed = [p for p in sys.path
               if p and os.path.normcase(os.path.abspath(p)) ==
               os.path.normcase(os.path.abspath(REPO))]
    for path in removed:
        sys.path.remove(path)
    return len(removed)


def verify(label, archive, rooted):
    path = os.path.join(REPO, archive.replace("/", os.sep))
    assert os.path.isfile(path), f"{label}: Archiv fehlt: {path}"

    with zipfile.ZipFile(path) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
    log(f"  [{label}] {os.path.basename(path)} | {len(names)} Dateien")
    assert not any("__pycache__" in n for n in names), f"{label}: __pycache__ im Archiv"
    assert not any(n.endswith((".pyc", ".pyo")) for n in names), f"{label}: .pyc im Archiv"

    if rooted:
        assert "__init__.py" in names, f"{label}: __init__.py nicht auf der Wurzel"
        assert "blender_manifest.toml" in names, f"{label}: Manifest nicht auf der Wurzel"
        assert not any(n.startswith(PACKAGE + "/") for n in names), \
            f"{label}: Package-Ordner im Extension-Archiv"
    else:
        assert f"{PACKAGE}/__init__.py" in names, \
            f"{label}: {PACKAGE}/__init__.py fehlt"
        assert not any(n == "blender_manifest.toml" for n in names), \
            f"{label}: Manifest gehoert nicht ins Legacy-Archiv"

    tmp = tempfile.mkdtemp(prefix=f"ah_zip_{label}_")
    unload_package()
    removed = isolate_from_workcopy()

    if rooted:
        target = os.path.join(tmp, PACKAGE)
        os.makedirs(target)
    else:
        target = tmp
    with zipfile.ZipFile(path) as zf:
        zf.extractall(target)

    sys.path.insert(0, tmp)
    importlib.invalidate_caches()
    module = importlib.import_module(PACKAGE)

    origin = os.path.normcase(os.path.abspath(module.__file__))
    assert origin.startswith(os.path.normcase(os.path.abspath(tmp))), \
        f"{label}: getestet wird nicht das Archiv: {module.__file__}"
    log(f"    importiert aus: {os.path.relpath(module.__file__, tmp)} "
        f"({removed} Arbeitsstand-Pfade aus sys.path entfernt)")

    module.register()
    assert hasattr(bpy.types.Scene, "outliner_auto_highlight"), f"{label}: Scene-Property fehlt"
    assert hasattr(bpy.types.Scene, "outliner_auto_highlight_collapse"), \
        f"{label}: Collapse-Property fehlt"
    assert hasattr(bpy.ops.outliner, "auto_highlight_sync"), f"{label}: Sync-Operator fehlt"
    assert hasattr(bpy.ops.outliner, "auto_highlight_apply_all"), f"{label}: Apply-Operator fehlt"

    from outliner_highlight import ui, watcher
    assert bpy.app.timers.is_registered(watcher._tick), f"{label}: Timer laeuft nicht"
    assert ui._draw_header in draw_funcs(bpy.types.OUTLINER_HT_header), f"{label}: Header-Hook fehlt"
    assert ui._draw_filter in draw_funcs(bpy.types.OUTLINER_PT_filter), f"{label}: Filter-Hook fehlt"
    log("    registriert: 2 Scene-Properties, 2 Operatoren, Timer, 2 UI-Hooks")

    module.unregister()
    assert not bpy.app.timers.is_registered(watcher._tick), f"{label}: Timer ueberlebt unregister"
    assert ui._draw_header not in draw_funcs(bpy.types.OUTLINER_HT_header), \
        f"{label}: Header-Hook ueberlebt unregister"
    log("    unregister: Timer und UI-Hooks wieder weg")

    unload_package()
    sys.path.remove(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def restore_workcopy():
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    importlib.invalidate_caches()
    from outliner_highlight import watcher

    sys.modules[PACKAGE].register()
    assert bpy.app.timers.is_registered(watcher._tick), "Arbeitsstand nicht registriert"
    log("  Arbeitsstand wieder registriert")


try:
    for label, archive, rooted in archives():
        verify(label, archive, rooted)
    restore_workcopy()
    log("ZIP_VERIFY_OK")
except AssertionError as exc:
    log(f"FAIL: {exc}")
except Exception:
    log("FAIL:\n" + traceback.format_exc())

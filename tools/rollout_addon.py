"""Make the running Blender session execute the code that is on disk now.

Run from the Text Editor (Alt+P), from the Python Console via
``exec(open(...).read())``, or headless with ``blender --python``.

Why this exists: Python caches imported modules in ``sys.modules``, and an
add-on is imported once. The classes and functions the session keeps using are
objects from that one import, so a changed file on disk is not re-read —
everything the session then checks is *yesterday's logic*. Seeing the add-on
behave in Blender is not evidence that the current source behaves that way.

Two things this add-on needs beyond a plain re-import:

* The ``load_post`` handler in :mod:`properties` appends a bound function. A
  disabled-and-re-enabled cycle runs ``unregister`` first, so the old reference
  is removed; a bare ``sys.modules`` purge would not do that, and the list would
  collect one dead handler per reload.
* The watcher owns a persistent timer. Re-registering is guarded by
  ``is_registered``, so the fallback path below cannot stack timers.

``register()`` is safe to call twice — both the add-on and the timer check
whether they are already live.
"""

from __future__ import annotations

import glob
import importlib
import os
import sys
import time

import bpy

MODULE = "outliner_highlight"


def candidate_roots() -> list:
    """Folders that could be the parent of the package, most likely first.

    Every candidate is validated against the filesystem by :func:`package_root`,
    so a wrong guess is harmless rather than fatal.
    """
    roots = []

    # 1) The already-imported package knows where it lives. During a reload this
    #    is the strongest source and the only one that survives being exec'd
    #    from a string — see (2).
    module_file = getattr(sys.modules.get(MODULE), "__file__", None)
    if module_file:
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(module_file))))

    # 2) This script's own location: correct when run as a file, misleading when
    #    exec'd, because the caller's ``__file__`` leaks into the namespace. A
    #    rollout exec'd from the MCP bridge resolved to the bridge's directory
    #    and reported "cannot find the package" — hence (1) and (3).
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        roots.append(os.path.dirname(here))
    except NameError:
        pass

    # 3) sys.path: a session that has run this before still has the root on it.
    roots.extend(entry for entry in list(sys.path) if entry)

    cwd = os.getcwd()
    roots.append(cwd)
    roots.append(os.path.dirname(cwd))

    # 4) Last resort for a session started somewhere unrelated. Bounded: the
    #    earlier candidates answer in practice, so this only runs when they
    #    cannot, and then a few hundred stats are cheaper than a hard failure.
    for base, patterns in (
        (os.path.join(os.path.expanduser("~"), "Dev"), ("*", "*/*", "*/*/*")),
        (os.path.join(os.path.expanduser("~"), "Dev", "blender-tools", "plugins"), ("*",)),
    ):
        if not os.path.isdir(base):
            continue
        for pattern in patterns:
            for candidate in sorted(glob.glob(os.path.join(base, pattern))):
                if os.path.isdir(candidate):
                    roots.append(candidate)

    return roots


def package_root(name: str) -> str:
    """The directory that has to be on ``sys.path`` for ``name`` to import."""
    for root in candidate_roots():
        if root and os.path.isdir(os.path.join(root, name)):
            return root
    raise RuntimeError(f"cannot find the package {name!r}; run this from the plugin folder")


def reload_package(name: str, root: str) -> str:
    import addon_utils

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        enabled, _ = addon_utils.check(name)
    except Exception:
        enabled = False

    if enabled:
        try:
            bpy.ops.preferences.addon_disable(module=name)
            bpy.ops.preferences.addon_enable(module=name)
            return "disabled and enabled as an add-on"
        except Exception as exc:  # noqa: BLE001
            print(f"    add-on reload failed ({type(exc).__name__}); purging modules instead")

    # Unregister the copy still sitting in sys.modules before dropping it.
    # Blender holds the watcher's timer as a function object, not by name, so a
    # bare purge leaves the previous _tick registered: is_registered() then
    # reports False for the *new* function, register() adds a second timer, and
    # both run — one of them against dead classes. The addon_disable path above
    # does this for us; this branch has to do it itself.
    stale = sys.modules.get(name)
    if stale is not None and hasattr(stale, "unregister"):
        try:
            stale.unregister()
        except Exception as exc:  # noqa: BLE001
            print(f"    stale unregister failed ({type(exc).__name__}); continuing")

    for entry in [m for m in list(sys.modules) if m == name or m.startswith(name + ".")]:
        del sys.modules[entry]
    importlib.invalidate_caches()
    package = importlib.import_module(name)
    if hasattr(package, "register"):
        package.register()
    return "sys.modules purged, imported fresh, registered"


def stamp(root: str, name: str) -> None:
    """Size and modified time per source file, so staleness is visible."""
    newest = 0.0
    for path in sorted(glob.glob(os.path.join(root, name, "**", "*.py"), recursive=True)):
        info = os.stat(path)
        newest = max(newest, info.st_mtime)
        print(
            f"    {os.path.relpath(path, root):<44} {info.st_size:>6} B  "
            f"{time.strftime('%H:%M:%S', time.localtime(info.st_mtime))}"
        )
    age = time.time() - newest
    if age < 120:
        print("    newest source: just now")
    else:
        # Not a warning. A rollout with nothing edited in the package is normal
        # — editing tools/ or scripts/ does not touch these files — and the
        # message only has to make a *stale* timestamp interpretable.
        print(f"    newest source: {age / 60:.0f} min old (nothing in the package edited)")


def main() -> None:
    name = MODULE
    root = package_root(name)
    print(f"  rolling out {name!r} from {root}")
    print(f"  reload: {reload_package(name, root)}")
    print("  sources now in effect:")
    stamp(root, name)
    print("  done -- run this again after every code change.")


main()

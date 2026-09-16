"""Build the installable add-on zip.

Run:  python tools/build_release.py [--check]

Why the archive layout is not a free choice
-------------------------------------------

Blender's *Install from Disk* unpacks a zip into ``scripts/addons/`` and imports
the top-level package it finds there. So ``outliner_highlight/`` has to sit at
the **root** of the archive. Wrapping it in a ``outliner-highlight/`` folder —
the natural thing to do, since that is what the repo is called — produces an
add-on that installs without a single error message and never shows up in the
list. ``--check`` exists to catch that class of mistake rather than to be tidy.

Version comes from ``bl_info``
------------------------------

``bl_info["version"]`` is the one place the version lives; it is parsed out of
the source with :mod:`ast` instead of being imported, so the build works without
Blender and without adding the package to ``sys.path``. Restating the version in
this file would guarantee the day the two disagree.

``--check`` compares the archive against the files on disk
---------------------------------------------------------

Not the zip bytes — those move with compression and timestamps — but the set of
members with their sizes and content hashes. That is what "the zip is stale"
actually means, and it is the only failure mode that matters here: a released
zip quietly missing the last fix.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import sys
import zipfile
from pathlib import Path

PACKAGE = "outliner_highlight"
REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"

# Never shipped. __pycache__ most of all: it is regenerated on import, it bloats
# the archive, and on a mixed-version machine it can shadow the real source.
EXCLUDE_DIRS = {"__pycache__", ".git", ".zcode", "dist", "docs", "scripts", "tools"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".blend1", ".blend2"}


def read_bl_info(package: Path) -> dict:
    source = (package / "__init__.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = getattr(node, "targets", [])
        if any(getattr(t, "id", None) == "bl_info" for t in targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"no bl_info found in {package / '__init__.py'}")


def sources(package: Path) -> list[Path]:
    found = []
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(REPO).parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        found.append(path)
    return found


def manifest(package: Path) -> dict:
    """arcname -> (size, sha256) for everything the archive should contain."""
    rows = {}
    for path in sources(package):
        data = path.read_bytes()
        arc = path.relative_to(REPO).as_posix()
        rows[arc] = (len(data), hashlib.sha256(data).hexdigest())
    return rows


def archive_manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        rows = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            data = zf.read(info.filename)
            rows[info.filename] = (len(data), hashlib.sha256(data).hexdigest())
        return rows


def build(package: Path, target: Path) -> dict:
    rows = manifest(package)
    if not rows:
        raise SystemExit(f"nothing to pack under {package}")
    if f"{PACKAGE}/__init__.py" not in rows:
        raise SystemExit(
            f"{PACKAGE}/__init__.py is not at the archive root — Blender would "
            "install this and never list it"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc in sorted(rows):
            zf.write(REPO / arc, arc)
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing zip matches the sources instead of rebuilding",
    )
    args = parser.parse_args(argv)

    package = REPO / PACKAGE
    info = read_bl_info(package)
    version = ".".join(str(part) for part in info["version"])
    target = DIST / f"{PACKAGE.replace('_', '-')}-{version}.zip"

    if args.check:
        if not target.exists():
            print(f"  {target.name} does not exist — run without --check")
            return 1
        want = manifest(package)
        have = archive_manifest(target)
        missing = sorted(set(want) - set(have))
        extra = sorted(set(have) - set(want))
        changed = sorted(k for k in set(want) & set(have) if want[k] != have[k])
        if missing or extra or changed:
            for label, names in (("missing from zip", missing),
                                 ("not in sources", extra),
                                 ("content differs", changed)):
                for name in names:
                    print(f"  {label}: {name}")
            print(f"  {target.name} is STALE — rebuild it")
            return 1
        print(f"  {target.name} matches the sources ({len(want)} files)")
        return 0

    rows = build(package, target)
    size = target.stat().st_size
    print(f"  {info['name']} {version}  (blender {info['blender']})")
    print(f"  {target.relative_to(REPO).as_posix()}  {size:,} B  {len(rows)} files")
    for arc in sorted(rows):
        print(f"    {arc:<44} {rows[arc][0]:>6} B")
    print("  install with Blender > Preferences > Add-ons > Install from Disk")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

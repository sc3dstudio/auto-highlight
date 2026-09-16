"""Build the two installable zips: a Blender extension and a classic add-on.

Run:  python tools/build_release.py [--check]

Why two artifacts
-----------------

Blender 4.2 replaced add-ons with extensions, and the two are packaged
differently:

* **extension** — the archive root *is* the package: ``__init__.py`` and
  ``blender_manifest.toml`` sit side by side at the top, with no wrapper folder.
  Install via *Get Extensions > Install from Disk*, or by dropping the zip onto
  Blender.
* **classic add-on** — the archive contains a package folder
  (``outliner_highlight/``) which Blender unpacks into ``scripts/addons/`` and
  imports by that name. Needed for a hand-managed ``scripts/addons`` setup, and
  for anything older than 4.2.

Both are built from the same source tree, so they cannot drift. The manifest is
excluded from the classic zip on purpose: a legacy add-on folder that carries a
``blender_manifest.toml`` is a valid and ambiguous thing to hand Blender, and
nothing here needs it.

Version comes from ``bl_info``
------------------------------

``bl_info["version"]`` is the one place the version lives; it is parsed out of
the source with :mod:`ast` rather than being imported, so the build works
without Blender and without adding the package to ``sys.path``. The manifest
repeats it for the extension format and ``--check`` fails when the two disagree,
because that is a drift nobody would notice until an update misbehaved.

``--check``
-----------

Compares each archive against the files on disk — not the zip bytes, which move
with compression and timestamps, but the member set with sizes and content
hashes. That is what "the zip is stale" actually means, and it is the failure
that matters: a release quietly missing the last fix.

The extension is validated by Blender itself, which knows the format better than
this script does::

    blender --command extension validate dist/outliner-highlight-0.1.0.zip
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import sys
import tomllib
import zipfile
from pathlib import Path

PACKAGE = "outliner_highlight"
REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"

MANIFEST = "blender_manifest.toml"

# Never shipped. __pycache__ most of all: it is regenerated on import, it bloats
# the archive, and on a mixed-version machine it can shadow the real source.
EXCLUDE_DIRS = {"__pycache__", ".git", ".zcode"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".blend1", ".blend2"}


def read_bl_info(package: Path) -> dict:
    source = (package / "__init__.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = getattr(node, "targets", [])
        if any(getattr(t, "id", None) == "bl_info" for t in targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"no bl_info found in {package / '__init__.py'}")


def read_manifest(package: Path) -> dict:
    path = package / MANIFEST
    if not path.is_file():
        raise SystemExit(f"no {MANIFEST} in {package}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def package_files(package: Path) -> list[Path]:
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


def members(package: Path, *, root_level: bool, with_manifest: bool) -> dict:
    """arcname -> bytes for one of the two layouts."""
    rows = {}
    for path in package_files(package):
        relative = path.relative_to(package)
        if not with_manifest and relative.name == MANIFEST:
            continue
        arc = relative.as_posix() if root_level else f"{PACKAGE}/{relative.as_posix()}"
        rows[arc] = path.read_bytes()
    return rows


def layouts(package: Path) -> dict:
    return {
        "extension": members(package, root_level=True, with_manifest=True),
        "legacy": members(package, root_level=False, with_manifest=False),
    }


def hash_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_members(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        return {
            info.filename: zf.read(info.filename)
            for info in zf.infolist()
            if not info.is_dir()
        }


def write(target: Path, rows: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc in sorted(rows):
            zf.writestr(arc, rows[arc])


def check(target: Path, rows: dict) -> list:
    if not target.exists():
        return [f"{target.name} does not exist — run without --check"]
    have = archive_members(target)
    problems = []
    for name in sorted(set(rows) - set(have)):
        problems.append(f"{target.name}: missing from zip: {name}")
    for name in sorted(set(have) - set(rows)):
        problems.append(f"{target.name}: not in sources: {name}")
    for name in sorted(set(have) & set(rows)):
        if hash_of(have[name]) != hash_of(rows[name]):
            problems.append(f"{target.name}: content differs: {name}")
    return problems


def targets(version: str) -> dict:
    base = f"outliner-highlight-{version}"
    return {"extension": DIST / f"{base}.zip", "legacy": DIST / f"{base}-legacy.zip"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing zips match the sources instead of rebuilding",
    )
    args = parser.parse_args(argv)

    package = REPO / PACKAGE
    info = read_bl_info(package)
    manifest = read_manifest(package)
    version = ".".join(str(part) for part in info["version"])
    files = targets(version)
    rows = layouts(package)

    # The two files that state the version have to agree; only one of them is
    # read at a time, so a drift here is invisible until an update misbehaves.
    if manifest["version"] != version:
        print(f"  VERSION MISMATCH: bl_info {version} vs manifest {manifest['version']}")
        return 1
    if manifest["id"] != PACKAGE:
        print(f"  ID MISMATCH: manifest id {manifest['id']!r} vs package {PACKAGE!r}")
        return 1

    # Not every Blender that supports extensions accepts every license. Older
    # ones reject an add-on that is not GPL-3.0-or-later outright -- "license for
    # add-ons must be GPL v3.0 or later" -- while 5.2 still accepts the
    # GPL-2.0-or-later that matches Blender's own source. So a build checked only
    # against a local 5.x will happily ship a manifest that other versions
    # refuse, which is exactly what 0.1.0 did.
    portable = {"SPDX:GPL-3.0-or-later"}
    declared = set(manifest.get("license", []))
    if manifest.get("type") == "add-on" and not (declared & portable):
        print(f"  LICENSE NOT PORTABLE: {sorted(declared)}")
        print(f"  an add-on needs {sorted(portable)} to install on every Blender "
              "that supports extensions")
        return 1

    if args.check:
        problems = []
        for kind, target in files.items():
            problems += check(target, rows[kind])
        if problems:
            for line in problems:
                print(f"  {line}")
            print("  the zips are STALE — rebuild them")
            return 1
        for kind, target in files.items():
            print(f"  {target.name} matches the sources ({len(rows[kind])} files)")
        return 0

    print(f"  {info['name']} {version}  (blender {info['blender']})")
    for kind, target in files.items():
        write(target, rows[kind])
        print(f"  {target.relative_to(REPO).as_posix()}  {target.stat().st_size:,} B  "
              f"{len(rows[kind])} files  [{kind}]")
    for arc in sorted(rows["extension"]):
        print(f"    extension root: {arc}")

    blender_min = manifest["blender_version_min"]
    print(f"  extension: Blender {blender_min}+, Get Extensions > Install from Disk")
    print(f"  legacy:    {info['blender']}+, Preferences > Add-ons > Install from Disk")
    print("  validate the extension with:")
    print(f"    blender --command extension validate "
          f"{files['extension'].relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

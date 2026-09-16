"""Upload a new version of this extension to extensions.blender.org.

Run:  BLENDER_EXTENSIONS_TOKEN=... python tools/publish_extension.py \\
          --notes "what changed"        # or --notes-file path/to/notes.md

What the API can and cannot do
------------------------------

Measured against the live API, not read off a page:

* **Uploading a version works.** ``POST /api/v1/extensions/<id>/versions/upload/``
  with a bearer token, a ``version_file`` and ``release_notes``. Without a token
  it answers 401.
* **Creating an extension does not.** ``OPTIONS /api/v1/extensions/`` returns
  ``Allow: GET, HEAD, OPTIONS`` and a POST is 405. There is no create endpoint.
* **Nor does any of the page metadata.** The public listing exposes only what the
  manifest carries — id, name, tagline, version, license, tags, type, website,
  blender_version_min — and nothing else. Description, support URL, icon,
  featured image and previews are site content and exist only in the web
  interface.

So the first submission has to be done by hand in the browser, with the texts
from ``docs/extension-submission.md``. Every version after that is this script.

The token
---------

From https://extensions.blender.org/settings/tokens/ — it belongs to the
account, so it is read from the environment and never written anywhere. The
script refuses to run without it rather than sending a request that would 401.

``--dry-run`` prints exactly what would be sent, without a token and without a
network call, so the command can be checked before it counts.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "outliner_highlight" / "blender_manifest.toml"
API = "https://extensions.blender.org/api/v1/extensions"
TOKEN_ENV = "BLENDER_EXTENSIONS_TOKEN"


def read_manifest() -> dict:
    """Minimal reader: the two keys needed, without tomllib's version floor."""
    import tomllib

    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))


def read_bl_info_version() -> str:
    source = (REPO / "outliner_highlight" / "__init__.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if any(getattr(t, "id", None) == "bl_info" for t in getattr(node, "targets", [])):
            info = ast.literal_eval(node.value)
            return ".".join(str(part) for part in info["version"])
    raise SystemExit("no bl_info version found")


def multipart(fields: dict, files: dict) -> tuple:
    boundary = "----outlinerhighlight" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += value.encode("utf-8") + b"\r\n"
    for name, (filename, data, ctype) in files.items():
        out += f"--{boundary}\r\n".encode()
        out += (f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n').encode()
        out += f"Content-Type: {ctype}\r\n\r\n".encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return boundary, bytes(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--notes", help="release notes, markdown")
    parser.add_argument("--notes-file", type=Path, help="file to read the notes from")
    parser.add_argument("--version-file", type=Path,
                        help="the extension zip (default: the built one in dist/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the request without sending it")
    args = parser.parse_args(argv)

    manifest = read_manifest()
    extension_id = manifest["id"]
    version = manifest["version"]

    bl_info_version = read_bl_info_version()
    if bl_info_version != version:
        print(f"  VERSION MISMATCH: bl_info {bl_info_version} vs manifest {version}")
        return 1

    if args.notes_file:
        notes = args.notes_file.read_text(encoding="utf-8")
    elif args.notes:
        notes = args.notes
    else:
        print("  need --notes or --notes-file")
        return 1

    version_file = args.version_file or (
        REPO / "dist" / f"outliner-highlight-{version}.zip")
    if not version_file.is_file():
        print(f"  missing version file: {version_file}")
        print("  build it first: python tools/build_release.py")
        return 1

    url = f"{API}/{extension_id}/versions/upload/"
    payload = version_file.read_bytes()
    print(f"  extension : {extension_id}")
    print(f"  version   : {version}")
    print(f"  file      : {version_file.name} ({len(payload):,} B)")
    print(f"  notes     : {len(notes)} characters")
    print(f"  endpoint  : POST {url}")

    if args.dry_run:
        print("  --dry-run: nothing sent")
        return 0

    token = os.environ.get(TOKEN_ENV)
    if not token:
        print(f"  {TOKEN_ENV} is not set — no request sent")
        print("  token: https://extensions.blender.org/settings/tokens/")
        return 1

    boundary, body = multipart(
        {"release_notes": notes},
        {"version_file": (version_file.name, payload, "application/zip")},
    )
    request = Request(url, data=body, method="POST")
    request.add_header("Authorization", f"bearer {token}")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urlopen(request, timeout=120) as response:
            print(f"  HTTP {response.status}")
            print(response.read().decode("utf-8", "replace")[:2000])
    except HTTPError as exc:
        print(f"  HTTP {exc.code} {exc.reason}")
        detail = exc.read().decode("utf-8", "replace")
        print(detail[:2000])
        if exc.code in (401, 403):
            print("  the token was rejected — check it, and that the extension exists")
        elif exc.code == 404:
            print("  no such extension — create it in the web interface first")
        return 1
    except URLError as exc:
        print(f"  network failure: {exc.reason}")
        return 1

    print("  uploaded")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

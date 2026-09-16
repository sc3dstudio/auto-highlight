"""Build the images the extensions.blender.org submission form asks for.

Run:  python tools/make_assets.py

Writes into ``assets/platform/``:

| File | Where it goes |
| --- | --- |
| ``icon-256.png`` | the *Icon* field, 256 x 256 |
| ``featured-1920x1080.png`` | the *Featured image* field, 16:9 |
| ``preview-1-before-after.png`` | first *Preview*, 16:9 |
| ``preview-2-nested.png`` | second *Preview*, 16:9 |

Why the icon is drawn and the rest is composed
----------------------------------------------

The previews are screenshots of the real add-on working, so they are *composed*
from the captures in ``assets/`` — anything drawn from scratch there would be a
lie about what the add-on looks like.

The icon cannot be a screenshot: at 32 px a captured Outliner is a grey smear.
It is drawn pixel by pixel instead — three rows, the middle one selected, which
is the whole product in one glyph.

The previews are placed on a dark canvas rather than shown flush, because a
657 x 540 capture in a 16:9 frame otherwise floats in the middle with ragged
edges. Padding them onto a common background makes the set look deliberate.

Windows path note
-----------------

``ffmpeg`` filter graphs treat ``:`` as an option separator, so an absolute
Windows path in ``fontfile=`` or ``textfile=`` needs escaping and every attempt
to get that right through a shell is a coin flip. This script sidesteps it: the
font, the sources and the text files are copied into a temporary directory and
ffmpeg runs with that directory as its working directory, so every path in the
command is a bare filename.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "assets"
PLATFORM = ASSETS / "platform"

FONT = Path("C:/Windows/Fonts/arialbd.ttf")
FONT_REGULAR = Path("C:/Windows/Fonts/arial.ttf")

BACKDROP = "0x17171a"
CANVAS = (1920, 1080)


# --------------------------------------------------------------------- icon

def _rounded_rect_sdf(px, py, x, y, w, h, r):
    """Signed distance to a rounded rectangle; negative inside."""
    cx, cy = x + w / 2, y + h / 2
    hw, hh = w / 2, h / 2
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _blend(px, i, colour, alpha):
    if alpha <= 0.0:
        return
    r, g, b = colour
    inv = 1.0 - alpha
    px[i] = int(px[i] * inv + r * alpha)
    px[i + 1] = int(px[i + 1] * inv + g * alpha)
    px[i + 2] = int(px[i + 2] * inv + b * alpha)
    px[i + 3] = int(px[i + 3] * inv + 255 * alpha)


def _shape(rows, box, colour, radius):
    x, y, w, h = box
    for py in range(max(0, int(y) - 2), min(len(rows), int(y + h) + 2)):
        row = rows[py]
        for pxi in range(max(0, int(x) - 2), min(len(row) // 4, int(x + w) + 2)):
            d = _rounded_rect_sdf(pxi + 0.5, py + 0.5, x, y, w, h, radius)
            alpha = min(max(0.5 - d, 0.0), 1.0)
            if alpha > 0.0:
                _blend(row, pxi * 4, colour, alpha)


def _write_png(path, width, height, rows):
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def make_icon(path: Path) -> None:
    size = 256
    rows = [bytearray(size * 4) for _ in range(size)]

    # Rounded backdrop, Blender-dark.
    _shape(rows, (8, 8, 240, 240), (27, 27, 31), 52)
    # The selected row: a full-width band, the way the Outliner draws it.
    _shape(rows, (22, 104, 212, 48), (61, 99, 168), 12)
    # Three name rows. The middle one is the selection, so it is the bright one.
    _shape(rows, (42, 68, 104, 16), (141, 141, 150), 8)
    _shape(rows, (42, 120, 140, 16), (238, 242, 248), 8)
    _shape(rows, (42, 172, 84, 16), (141, 141, 150), 8)

    _write_png(path, size, size, rows)


# ---------------------------------------------------------------- composing

def _fontconfig_env(work: Path) -> dict:
    """A minimal fontconfig, because some ffmpeg builds ship without one.

    ``drawtext`` fails with ``Fontconfig error: Cannot load default config
    file`` on the gyan Windows build used here. ``fontfile=`` is a FreeType path
    and needs no fontconfig to *find* a font, but the filter still initialises
    fontconfig, so it has to be given something valid. One directory and one
    cache directory are enough.
    """
    config = work / "fonts.conf"
    config.write_text(
        '<?xml version="1.0"?>\n'
        "<fontconfig>\n"
        f"  <dir>{Path('C:/Windows/Fonts').as_posix()}</dir>\n"
        f"  <cachedir>{(work / 'fc-cache').as_posix()}</cachedir>\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )
    (work / "fc-cache").mkdir(exist_ok=True)
    env = dict(os.environ)
    # Forward slashes: fontconfig parses these paths itself, and a backslash
    # path from str() is not a Windows path to it.
    env["FONTCONFIG_FILE"] = config.as_posix()
    env["FONTCONFIG_PATH"] = work.as_posix()
    return env


def _run(args, cwd):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=cwd, capture_output=True, text=True, env=_fontconfig_env(Path(cwd)),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ffmpeg failed (exit {result.returncode}):\n{' '.join(args)}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )


def _fonts(work: Path) -> None:
    """Copy both fonts in. Must run before *any* ffmpeg call that draws text.

    A ``fontfile=`` pointing at a file that is not there does not produce
    "no such file" — ffmpeg dies with an access violation, exit code
    3221225477, and prints nothing at all. That is how this cost an hour: the
    crash looks like a broken filter graph, and the graph is fine.
    """
    shutil.copy(FONT, work / "bold.ttf")
    shutil.copy(FONT_REGULAR, work / "regular.ttf")


def _stage(work: Path, sources: dict) -> None:
    for name, source in sources.items():
        shutil.copy(source, work / name)


def _textfile(work: Path, name: str, text: str) -> str:
    (work / name).write_text(text, encoding="utf-8")
    return name


def _half_pad() -> str:
    """Centre a capture inside one half of the 16:9 canvas.

    Padding to the *half* width, not to the canvas width. Padding both halves to
    1920 and then stacking them produced a 3840 x 1080 file — which still looked
    correct in a viewer that scales to fit, and so was easy to ship.
    """
    half = CANVAS[0] // 2
    return (f"scale={half}:-1,pad={half}:{CANVAS[1]}:(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKDROP}")


def make_featured(work: Path, after: Path, path: Path) -> None:
    title = _textfile(work, "title.txt", "Outliner Auto-Highlight")
    sub = _textfile(work, "sub.txt",
                    "Reveals the active object. Closes everything else.")
    meta = _textfile(work, "meta.txt", "Blender 4.2+")
    _stage(work, {"after.png": after})

    # The screenshot width is derived from its height rather than typed in: at
    # 812 px tall this 657-wide capture is 988 px wide and ran 78 px off the
    # right edge of the canvas, which is not visible until you look at the file.
    shot_h = 730
    shot_w = round(shot_h * 657 / 540)
    shot_x = CANVAS[0] - shot_w - 72
    shot_y = (CANVAS[1] - shot_h) // 2

    # The text column on the left is what makes this read as a banner rather
    # than as a screenshot with a dark border.
    graph = (
        f"[0:v]scale=-1:{shot_h}[shot];"
        f"color=c={BACKDROP}:s={CANVAS[0]}x{CANVAS[1]}[bg];"
        f"[bg][shot]overlay=x={shot_x}:y={shot_y}[withshot];"
        f"[withshot]"
        f"drawtext=fontfile=bold.ttf:textfile={title}:x=110:y=376:"
        f"fontsize=68:fontcolor=0xf2f4f8,"
        f"drawtext=fontfile=regular.ttf:textfile={sub}:x=112:y=478:"
        f"fontsize=32:fontcolor=0x9aa2ad,"
        f"drawtext=fontfile=bold.ttf:textfile={meta}:x=112:y=542:"
        f"fontsize=25:fontcolor=0xe87d0d"
        f"[out]"
    )
    # Passed inline rather than through -filter_complex_script: that option does
    # not exist in every build, and because every path inside the graph is a
    # bare filename in the working directory, there is nothing to escape.
    # -map is explicit: a labelled output in -filter_complex is otherwise left
    # unconnected and ffmpeg stops with "has output 0 (out) unconnected".
    _run(["-i", "after.png", "-filter_complex", graph, "-map", "[out]",
          "-frames:v", "1", path.as_posix()], work)


def make_before_after(work: Path, before: Path, after: Path, path: Path) -> None:
    left = _textfile(work, "left.txt", "Before")
    right = _textfile(work, "right.txt", "After Auto-Highlight")
    _stage(work, {"before.png": before, "after.png": after})

    half = CANVAS[0] // 2
    graph = (
        f"[0:v]{_half_pad()}[b];"
        f"[1:v]{_half_pad()}[a];"
        f"[b][a]hstack=inputs=2[two];"
        f"[two]"
        f"drawtext=fontfile=bold.ttf:textfile={left}:"
        f"x=({half}-text_w)/2:y=104:fontsize=44:fontcolor=0xdfe4ec,"
        f"drawtext=fontfile=bold.ttf:textfile={right}:"
        f"x={half}+({half}-text_w)/2:y=104:fontsize=44:fontcolor=0xdfe4ec"
        f"[out]"
    )
    _run(["-i", "before.png", "-i", "after.png", "-filter_complex", graph,
          "-map", "[out]", "-frames:v", "1", path.as_posix()], work)


def make_nested(work: Path, source: Path, path: Path) -> None:
    caption = _textfile(
        work, "cap.txt",
        "The parents open however deep the object sits — and nothing else does.",
    )
    shutil.copy(source, work / "nested.png")

    # Fitted into a box instead of scaled to fixed numbers: the crop is taller
    # than 16:9, and forcing it to the canvas ratio would stretch it.
    box_w, box_h = 1520, 780
    graph = (
        f"color=c={BACKDROP}:s={CANVAS[0]}x{CANVAS[1]}[bg];"
        f"[0:v]scale={box_w}:{box_h}:force_original_aspect_ratio=decrease[shot];"
        f"[bg][shot]overlay=x=(W-w)/2:y=(H-h)/2-45[withshot];"
        f"[withshot]drawtext=fontfile=regular.ttf:textfile={caption}:"
        f"x=(w-text_w)/2:y=1005:fontsize=34:fontcolor=0x9aa2ad[out]"
    )
    _run(["-i", "nested.png", "-filter_complex", graph, "-map", "[out]",
          "-frames:v", "1", path.as_posix()], work)


# ------------------------------------------------------------------- main

def require(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"missing source: {path}")
    return path


def main() -> int:
    PLATFORM.mkdir(parents=True, exist_ok=True)

    before = require(ASSETS / "before.png")
    after = require(ASSETS / "after.png")
    # Captured by scripts/capture_preview.py, which builds a nested demo tree in
    # a live session and removes it again. Committed rather than left in a temp
    # directory so this script is reproducible from the repository alone.
    nested = require(ASSETS / "nested.png")

    with tempfile.TemporaryDirectory(prefix="ah_assets_") as tmp:
        work = Path(tmp)
        _fonts(work)

        make_icon(PLATFORM / "icon-256.png")
        print("  icon-256.png")

        # Crop to the demo subtree. The rows above it are the user's own scene
        # and the rows below are unrelated objects; neither belongs in a preview.
        cropped = work / "nested_crop.png"
        _run(["-i", nested.as_posix(), "-vf", "crop=657:466:0:262",
              "-frames:v", "1", cropped.as_posix()], work)
        make_nested(work, cropped, PLATFORM / "preview-2-nested.png")
        print("  preview-2-nested.png")

        make_before_after(work, before, after, PLATFORM / "preview-1-before-after.png")
        print("  preview-1-before-after.png")

        make_featured(work, after, PLATFORM / "featured-1920x1080.png")
        print("  featured-1920x1080.png")

    for path in sorted(PLATFORM.iterdir()):
        print(f"  {path.name:<34} {path.stat().st_size:>8,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())

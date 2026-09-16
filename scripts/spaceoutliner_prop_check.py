"""Kann man eine bpy.props-Property auf SpaceOutliner registrieren?

Das entscheidet, ob der Auto-Highlight-Schalter pro Outliner (und damit pro
Datei gespeichert) leben kann wie im Original-Addon, oder ob er global in den
Addon-Preferences landen muss.

Laeuft im offenen Blender:  exec(open(PFAD).read())
"""

import bpy

lines = []


def say(text):
    lines.append(text)


so = bpy.types.SpaceOutliner

# --- 1) Property registrieren ---
try:
    so.ah_probe = bpy.props.BoolProperty(
        name="AH Probe", default=False, description="probe"
    )
    say("1) Zuweisung akzeptiert")
except Exception as exc:  # noqa: BLE001
    say(f"1) Zuweisung FAIL: {type(exc).__name__}: {exc}")

try:
    ids = [p.identifier for p in so.bl_rna.properties]
    say(f"2) in bl_rna.properties: {'ah_probe' in ids}")
except Exception as exc:  # noqa: BLE001
    say(f"2) bl_rna FAIL: {type(exc).__name__}: {exc}")

# --- 3) Auf einer lebenden Instanz setzen/lesen ---
win = bpy.context.window_manager.windows[0]
outs = [a for a in win.screen.areas if a.type == 'OUTLINER']
for area in outs:
    space = area.spaces.active
    mode = space.display_mode
    try:
        space.ah_probe = True
        got = space.ah_probe
        say(f"3) {mode}: set True -> read {got}")
        # zuruecksetzen
        space.ah_probe = False
    except Exception as exc:  # noqa: BLE001
        say(f"3) {mode} FAIL: {type(exc).__name__}: {exc}")

# --- 4) Zweiter Space desselben Areas darf unabhaengig sein ---
try:
    space = outs[0].spaces.active
    space.ah_probe = True
    others = [f"{s.display_mode}={getattr(s, 'ah_probe', 'n/a')}"
              for s in outs[0].spaces if s is not space]
    say(f"4) gleicher Area, andere Spaces: {others}")
    space.ah_probe = False
except Exception as exc:  # noqa: BLE001
    say(f"4) FAIL: {type(exc).__name__}: {exc}")

# --- 5) Outliner-Panels und Header, an die man sich haengen kann ---
panel_names = sorted(n for n in dir(bpy.types)
                     if n.startswith("OUTLINER_") and ("PT_" in n or "HT_" in n or "MT_" in n))
say(f"5) OUTLINER_ UI-Klassen: {panel_names}")

# --- 6) Aufraeumen ---
try:
    for area in outs:
        area.spaces.active.ah_probe = False
    del so.ah_probe
    say("6) Property wieder entfernt")
except Exception as exc:  # noqa: BLE001
    say(f"6) cleanup FAIL: {type(exc).__name__}: {exc}")

print("\n".join(lines))

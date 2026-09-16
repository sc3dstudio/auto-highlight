# outliner-highlight

Auto-Highlight for the Outliner: when the active object changes, the Outliner
scrolls to it, expands its parent collections, and — optionally — collapses
every other collection.

Built as a replacement for the paid
[Auto-Highlight in Outliner](https://superhivemarket.com/products/auto-highlight-in-outliner),
after checking what of it Blender already does itself.

**Status: built and verified in a live Blender 5.2.1 session.** Timer-driven
end to end, both switches, header button and Filters row, plus the counter-tests
below. Nothing is assumed from the paid add-on's description.

`bl_info` says Blender 3.3+, because nothing in the API surface used here is
newer than `temp_override` (3.2) and `show_one_level(open=...)` — but only 5.2.1
has actually been run. Treat the older claim as untested, not as support.

## Read this first: roughly two thirds of it is already in Blender

Blender 5.x has `SpaceOutliner.scroll_to_active` — *"Scroll the active item into
view when it changes outside of the Outliner"*. That is the headline feature,
native, and it is one checkbox in the Outliner's Filters popover. In the session
this was built in it was already switched on in the file.

`outliner.show_active()` — what that checkbox drives internally — also expands
the parent chain on its way down, so "expand the parents" is covered too.

What is **not** native is the third part: collapsing the collections that have
nothing to do with the selection. That is the one thing this add-on adds, and
it is the reason the code is shaped the way it is.

If all you want is scroll-plus-expand, you do not need this add-on — turn on
`scroll_to_active` in Outliner ▸ Filters and disable this one.

## Install

The add-on package is `outliner_highlight/`, so Blender needs it as
`scripts/addons/outliner_highlight` — a symlink or a copy of that directory:

```
ln -s <repo>/outliner_highlight "$HOME/.config/blender/5.2/scripts/addons/outliner_highlight"
mklink /D "%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\outliner_highlight" "<repo>\outliner_highlight"
```

For a dev session, put the **plugin root** (this folder) on `sys.path` and run
[`tools/rollout_addon.py`](tools/rollout_addon.py) from the Text Editor or the
Python Console. It re-imports and re-registers the add-on in place, so the
running session executes the source that is on disk *now*.

### Install from a build

```
python tools/build_release.py          # -> dist/outliner-highlight-0.1.0.zip
python tools/build_release.py --check  # fail if the zip is older than the sources
```

Then *Preferences ▸ Add-ons ▸ Install from Disk* on that zip.

The archive layout is not a free choice: Blender finds the package by importing
the top level of the zip, so `outliner_highlight/` has to sit at the **root**.
Wrapping it in a `outliner-highlight/` folder — the natural thing to do, since
that is the repo's name — installs without a single error and never appears in
the add-on list. `--check` exists for that mistake and for a released zip
quietly missing the last fix.

## Usage

| Where | What |
| --- | --- |
| Outliner ▸ Filters | **Auto-Highlight** — the main switch (per Scene, saved in the .blend) |
| Outliner ▸ Filters | **Collapse Others** — greys out until Auto-Highlight is on |
| Outliner ▸ Filters | **Reveal Active Object Now** — run it immediately instead of waiting for the next change |
| Outliner header | the same main switch as a compact icon toggle (`header_button`, on by default) |
| Preferences ▸ Add-ons | check interval, header button, defaults for new files, "enable on every scene in this file" |

There is no keymap bound by default — `outliner.auto_highlight_sync` can be
bound to a shortcut if you want one.

## Where it differs from the paid add-on

| Paid add-on | Here | Why |
| --- | --- | --- |
| toggle per Outliner editor | toggle per Scene (one per file) | `SpaceOutliner` refuses Python-defined properties — see below |
| "auto-expand parented objects" | not implemented | `show_one_level` applies to *every* entry, so there is no way to expand just the active object's children without flattening the rest |
| bone expansion in Pose Mode | not implemented | needs the armature's children open, which is the same missing primitive as above |
| "default state for new scenes" | "On in new files" preference | applied on `load_post` only when `bpy.data.filepath` is empty, so a saved file keeps its own setting |
| no focus jump when clicking in the Outliner | best effort | the add-on keys on the active object and cannot tell where the click came from; clicking the *same* object twice does nothing |

## Why the switch is not where it belongs

A per-Outliner property on `SpaceOutliner`, next to `use_sync_select`, is the
obvious home for it. Blender 5.2 will not take one. Measured, not guessed —
[`scripts/spaceoutliner_prop_check.py`](scripts/spaceoutliner_prop_check.py):

* `SpaceOutliner.ah_probe = bpy.props.BoolProperty(...)` is accepted at class
  level and never appears in `bl_rna.properties`.
* Setting it on a live space raises `AttributeError: 'SpaceOutliner' object
  attribute 'ah_probe' is read-only`.
* The type does not carry IDProperties either: `space.keys()` raises
  `bpy_struct.keys(): this type doesn't support IDProperties`.

So the state lives on the Scene: writable, saved in the .blend, same
user-visible result.

## The recipe, measured

Both screenshots and return values were taken in a live 5.2.1 session with a
deliberately deep tree (`Root > A > B > C > object` plus siblings), using
[`scripts/outliner_probe.py`](scripts/outliner_probe.py):

| Call | Result |
| --- | --- |
| `outliner.show_active()` | expands the whole parent chain, scrolls the row into view, highlights it. No arguments |
| `outliner.show_one_level(open=False)` | collapses *every* entry by one level; because it applies to all entries, one call flattens the whole tree |
| `outliner.item_openclose(all=True)` | returns `PASS_THROUGH` and changes nothing — it wants an input event, and in 5.2 it no longer even has the `open` argument |
| `show_one_level(open=False)` then `show_active()` | the feature: everything collapsed except the path to the active object |

## What was verified, and how

| Check | Evidence |
| --- | --- |
| fires on its own when the active object changes | changed the active object, left the script, let the timer run, then took a window screenshot — flat case and deep-nesting case |
| Collapse Others actually does something | counter-test: with it **off**, a fully expanded tree stayed fully expanded and only the active object was revealed |
| the header toggle renders | visible in every screenshot, top right of the Outliner header |
| the Filters row renders | `OUTLINER_PT_filter` draws inside a popover that cannot be opened from Python, so a temporary function appended to `OUTLINER_HT_header` called the real `_draw_filter` with a real `UILayout`: 6 redraws, no exception |
| no leak in the UI hooks | `OUTLINER_HT_header` / `OUTLINER_PT_filter` draw lists go 2 → 1 → 2 across unregister/register, and contain our function exactly once |
| the preferences class is valid | all four fields plus `bl_idname` present in the RNA |
| both operators actually run | not just registered: `apply_all` was invoked with every scene's flag off and left them on, returning `FINISHED` and its INFO report; `sync` was invoked with the tree collapsed **and the active object unchanged** — the one case the timer would skip — and the screenshot shows its collection reopened and its row highlighted |
| the built zip really installs | extracted `dist/outliner-highlight-0.1.0.zip` into a temp dir, put it on `sys.path`, imported and registered from there, then unregistered. It asserts `__file__` points **into the extraction** — the working copy sits next to it under the same module name, so without that check a green run would prove nothing |

The scripts are in [`scripts/`](scripts/) and are meant to be re-run after a
change, not read once.

## Files

```
outliner_highlight/__init__.py      bl_info and the registration order
outliner_highlight/properties.py    Scene flags, preferences, new-file defaults
outliner_highlight/watcher.py       the timer, the change check, the two operators
outliner_highlight/ui.py            Filters popover, header button, manual operators
tools/                              host-side: build the zip, reload a running session
scripts/                            inside Blender: the probes and checks behind every claim
```

The split is by where the code runs, not by subject: everything in `tools/` is
plain Python you run on the host, everything in `scripts/` needs a `bpy` and is
`exec`'d from the Text Editor or the Python Console.

| Script | Question it answers |
| --- | --- |
| `tools/build_release.py` | does an installable zip exist, and is it current |
| `tools/rollout_addon.py` | is the running session executing the source on disk |
| `scripts/outliner_probe.py` | what do `show_active`, `show_one_level` and `item_openclose` actually do |
| `scripts/spaceoutliner_prop_check.py` | can the switch live on `SpaceOutliner` (no) |
| `scripts/live_check.py` | does the timer reveal the active object, flat and nested |
| `scripts/verify_ui_and_collapse_off.py` | does the Filters row draw; does the collapse switch do anything |
| `scripts/verify_operators.py` | do both operators actually run, or only exist |
| `scripts/final_check.py` | do the UI hooks leak across a reload |
| `scripts/rollout_smoke.py` | does a real reload leave one timer and one set of hooks |
| `scripts/verify_zip.py` | does the built zip install and register like a real install |

## Not done yet

Ordered by how much they'd change the product, not by effort.

1. **Tell an Outliner click apart from a viewport selection.** `SpaceOutliner`
   itself knows — that is why the native `scroll_to_active` can say "outside of
   the Outliner" — but the flag is not readable from Python, and there is no
   mouse-position API a timer could use. With Collapse Others on, clicking a row
   in the Outliner therefore re-collapses the tree around it. The result is
   coherent (the clicked object is revealed) rather than broken, but it is a
   real difference from the paid add-on.
2. **A per-editor switch.** Blocked by the RNA restriction above; only a C-level
   `SpaceOutliner` property would fix it. A `WindowManager` dict keyed by space
   pointer would not survive a file reload or a saved layout.
3. **Verified on one Blender version.** 5.2.1 only. The realistic breakage is in
   `OUTLINER_HT_header` / `OUTLINER_PT_filter` still existing and in
   `show_one_level` keeping its `open` argument.
4. **Behaviour at scale is untested.** The tick is one attribute read per window,
   but `show_active` plus `show_one_level` runs on *every* active-object change.
   On an Outliner with tens of thousands of rows that is worth measuring before
   claiming it is free.
5. **Multiple scenes and view layers.** The flag is per Scene and the timer walks
   windows, each using its own scene, so it should be correct — nobody has tried
   it with two windows on two scenes.
6. **No keymap.** `outliner.auto_highlight_sync` can be bound by hand; nothing is
   bound by default so no shortcut is taken from another add-on.
7. **No release automation.** `build_release.py` makes the zip; nothing tags,
   bumps the version or attaches it to a GitHub release yet.

## Known limits

* **The timer does not run during modal operators.** That is deliberate — it
  means a box-select or a transform is never fought with — but it also means the
  reveal happens when the operator ends, not during it.
* **Selection changes alone do not trigger anything.** The Outliner highlights
  the active object, so extending a selection does not move the thing being
  followed. Ticking the checkbox forces one sync through `invalidate()`.
* **A rename does not trigger.** The change check keys on the object pointer,
  not its name, exactly so that renaming the active object does not flatten the
  tree when Collapse Others is on.

# Technical notes

How it works, what was measured, and what is still missing. The
[README](../README.md) is the user-facing version of this.

## Roughly two thirds of it was already in Blender

`SpaceOutliner.scroll_to_active` — *"Scroll the active item into view when it
changes outside of the Outliner"* — is the headline feature of the paid add-on
this replaces. It is native, and in the session this was built in it was already
switched on in the file. `outliner.show_active()`, which that checkbox drives
internally, also expands the parent chain on its way down.

What is not native is collapsing the unrelated collections. That is the one
thing this add-on adds, and it is the reason the code is shaped the way it is.

## The recipe, measured

Both the screenshots and the return values were taken in a live 5.2.1 session
with a deliberately deep tree (`Root > A > B > C > object` plus siblings), using
[`scripts/outliner_probe.py`](../scripts/outliner_probe.py):

| Call | Result |
| --- | --- |
| `outliner.show_active()` | expands the whole parent chain, scrolls the row into view, highlights it. No arguments |
| `outliner.show_one_level(open=False)` | collapses *every* entry by one level; because it applies to all entries, one call flattens the whole tree |
| `outliner.item_openclose(all=True)` | returns `PASS_THROUGH` and changes nothing — it wants an input event, and in 5.2 it no longer even has the `open` argument |
| `show_one_level(open=False)` then `show_active()` | the feature: everything closed except the path to the active object |

A repeating timer drives it rather than `depsgraph_update_post`. That handler
fires per dependency-graph evaluation — a mouse drag over the viewport is
hundreds of them — and running operators inside it is how you get re-entrant
updates. A timer also does not run while a modal operator is active, so a
transform or a box-select is never fought with.

## Why the switch is not where it belongs

A per-Outliner property on `SpaceOutliner`, next to `use_sync_select`, is the
obvious home for it. Blender 5.2 will not take one. Measured, not guessed —
[`scripts/spaceoutliner_prop_check.py`](../scripts/spaceoutliner_prop_check.py):

* `SpaceOutliner.ah_probe = bpy.props.BoolProperty(...)` is accepted at class
  level and never appears in `bl_rna.properties`.
* Setting it on a live space raises `AttributeError: 'SpaceOutliner' object
  attribute 'ah_probe' is read-only`.
* The type does not carry IDProperties either: `space.keys()` raises
  `bpy_struct.keys(): this type doesn't support IDProperties`.

So the state lives on the Scene: writable, saved in the .blend, same
user-visible result. The cost is granularity — the flag is per *file*, not per
*editor*.

## The change check

The trigger is the active object, keyed by its **pointer** rather than its name.
Name would be the obvious key and it is the wrong one: renaming the active object
in the Outliner (F2) would read as a change, and with Collapse Others on, a
rename would flatten the tree. A pointer is stable across a rename and changes on
a real switch.

Multi-selection deliberately triggers nothing: the Outliner highlights the active
object, so extending a selection does not move the thing being followed.

## What was verified, and how

| Check | Evidence |
| --- | --- |
| fires on its own when the active object changes | changed the active object, left the script, let the timer run, then took a window screenshot — flat case and deep-nesting case |
| Collapse Others actually does something | counter-test: with it **off**, a fully expanded tree stayed fully expanded and only the active object was revealed |
| the header toggle renders | visible in every screenshot, top right of the Outliner header |
| the Filters row renders | `OUTLINER_PT_filter` draws inside a popover that cannot be opened from Python, so a temporary function appended to `OUTLINER_HT_header` called the real `_draw_filter` with a real `UILayout`: 6 redraws, no exception |
| no leak in the UI hooks | `OUTLINER_HT_header` / `OUTLINER_PT_filter` draw lists go 2 → 1 → 2 across unregister/register, and contain the function exactly once |
| the preferences class is valid | all four fields plus `bl_idname` present in the RNA |
| both operators actually run | not just registered: `apply_all` was invoked with every scene's flag off and left them on; `sync` was invoked with the tree collapsed **and the active object unchanged** — the one case the timer skips — and the screenshot shows its collection reopened and its row highlighted |
| a reload leaves one timer | `scripts/rollout_smoke.py` holds the old function pointer and asserts `is_registered(old_tick)` is False afterwards. A duplicate timer cannot be found any other way: `bpy.app.timers` has no way to list what is registered |
| both zips really install | extracted into a temp dir, put on `sys.path`, imported and registered from there, then unregistered. Asserts `__file__` points **into the extraction** — the working copy sits next to it under the same module name, so without that check a green run would prove nothing |
| the extension format is valid | `blender --command extension validate`, which is Blender's own validator and stricter than anything written here |

### The one surface none of this renders

The preferences panel. Getting a real one needs an entry in
`preferences.addons`, which means enabling the add-on in the user's Blender
configuration — not something a verification script should write in order to
check a dozen lines of `layout.prop`. What is covered: the four fields and
`bl_idname` are confirmed present in the RNA, and the operator its button invokes
is verified by running it. The panel itself has never been on screen. That is a
stated gap, not a checked box.

## Packaging

Two artifacts from one source tree, because the two Blender mechanisms want
different archive layouts:

* **extension** — the archive root *is* the package: `__init__.py` and
  `blender_manifest.toml` at the top, no wrapper folder. Blender 4.2+.
* **classic add-on** — the archive contains `outliner_highlight/`, which Blender
  unpacks into `scripts/addons/`. The manifest is excluded here on purpose: a
  legacy add-on folder that carries one is a valid and ambiguous thing to hand
  Blender, and nothing here needs it.

Wrapping the extension in an `outliner-highlight/` folder — the natural thing to
do, since that is the repo's name — installs without a single error and never
appears in the list. `build_release.py --check` exists for that mistake and for a
released zip quietly missing the last fix.

Two things the official validator caught that hand-written checks did not:

* `tagline` has a **64 character** limit. The first one was 71 and the build was
  otherwise perfectly happy.
* The tag must be `User Interface`, not `Interface`. `Interface` is the value
  most add-ons copy around and is not in the accepted list — for extensions or
  for `bl_info["category"]`.

### And one thing it does not catch at all: the license

0.1.0 shipped as an extension with `license = ["SPDX:GPL-2.0-or-later"]`,
matching Blender's own source. On install, Blender answered:

```
Manifest value error: license for add-ons must be GPL v3.0 or later.
Additional license are possible, read the documentation.
e.g., ['SPDX:GPL-3.0-or-later'].
```

`blender --command extension validate` had said *Success parsing TOML* for that
same archive, and a hermetic install into a throwaway `BLENDER_USER_CONFIG`
(`repo-add`, then `install-file`) **also succeeded** on 5.2.1 — both with and
without `--enable`. GPL-2.0-or-later is still accepted by the version on this
machine, so the build that rejects it is not here to reproduce against; the
wording ("Additional license are possible") reads like a rule that was relaxed
after 4.x.

The fix is `SPDX:GPL-3.0-or-later`, which is accepted by both. `build_release.py`
now refuses to build an add-on with any other license, and says why — the failure
is otherwise invisible until somebody installs it on the wrong Blender.

The lesson is not "read the docs more carefully", it is that **validate is not
install**. The command validates the archive; the license rule is applied by the
installer, and the two disagree.

## Not done yet

Ordered by how much they would change the product, not by effort.

1. **Tell an Outliner click apart from a viewport selection.** `SpaceOutliner`
   itself knows — that is why the native `scroll_to_active` can say "outside of
   the Outliner" — but the flag is not readable from Python, and there is no
   mouse-position API a timer could use. The realistic route is an upstream
   request to expose that flag.
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
6. **No release automation.** `build_release.py` makes the zips; bumping the
   version is still hand-edited in two files, with a `--check` failure as the
   only guard against them drifting.

## Known limits

* **The timer does not run during modal operators.** Deliberate — a box-select or
  a transform is never fought with — but it also means the reveal happens when
  the operator ends, not during it.
* **Selection changes alone do not trigger anything.** Ticking the checkbox
  forces one sync by dropping the cached key.
* **A rename does not trigger.** See "the change check" above.

## Files

```
outliner_highlight/__init__.py      bl_info and the registration order
outliner_highlight/properties.py    Scene flags, preferences, new-file defaults
outliner_highlight/watcher.py       the timer, the change check, the two operators
outliner_highlight/ui.py            Filters popover, header button, manual operators
outliner_highlight/blender_manifest.toml   extension metadata
tools/                              host-side: build the zips, reload a running session
scripts/                            inside Blender: the probes and checks behind every claim
```

The split is by where the code runs, not by subject: everything in `tools/` is
plain Python you run on the host, everything in `scripts/` needs a `bpy` and is
`exec`'d from the Text Editor or the Python Console.

| Script | Question it answers |
| --- | --- |
| `tools/build_release.py` | do the installable zips exist, and are they current |
| `tools/make_assets.py` | are the submission images current, and to spec |
| `tools/rollout_addon.py` | is the running session executing the source on disk |
| `scripts/outliner_probe.py` | what do `show_active`, `show_one_level` and `item_openclose` actually do |
| `scripts/spaceoutliner_prop_check.py` | can the switch live on `SpaceOutliner` (no) |
| `scripts/live_check.py` | does the timer reveal the active object, flat and nested |
| `scripts/verify_ui_and_collapse_off.py` | does the Filters row draw; does the collapse switch do anything |
| `scripts/verify_operators.py` | do both operators actually run, or only exist |
| `scripts/final_check.py` | do the UI hooks leak across a reload |
| `scripts/rollout_smoke.py` | does a real reload leave one timer and one set of hooks |
| `scripts/verify_zip.py` | do both built archives install and register |
| `scripts/capture_preview.py` | take the nested-tree preview from a clean demo tree, not from a test fixture |

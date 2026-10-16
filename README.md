# Schiffy Sky Patrol

A toon sky-isles roguelike shooter starring Schiffy. Runs in the browser, nothing to install.

**Play:** https://aerynnnnn.github.io/schiffy-sky-patrol/

- WASD move, mouse aim and click to shoot, Space jump, Shift dash, right-click grenade, Q bark, E use, Tab upgrades, M map, Esc pause.
- Modes: Story (3 levels), Endless, Boss Rush and the Daily Challenge (open after clearing Level 1).
- Daily Challenge: one seeded run a day (UTC), the same isles and starting kit for everyone, scored by stages cleared.
- Schiffy's Home: the isle over the hub's east bridge. At its **Edit home** board you shop the home catalogue and arrange the isle: drag, stack, turn any way up and hover anything.
  - **Gold** (everyday furniture and garden): every coin you pick up in a run is also saved for the home.
  - **Paw Gems** (showpiece buildings): the premium currency (free playtest gems for now).
  - **Unlocks** (trophies): earned by milestones such as clearing each level, a Boss Rush, a 7-day Daily streak or finding every weapon.

## Models
The home catalogue's 32 items are modelled in Blender by `blender/build_home.py` (run it with Blender's Python module, `pip install bpy`), which writes `home.glb` and each item's collision boxes. The game embeds the meshopt-compressed GLB (`npx @gltf-transform/cli meshopt home.glb home_mo.glb`). `blender/render_home.py` renders a preview of every item.

This is a playtest build. Feedback welcome!

# Schiffy Sky Patrol

A toon sky-isles roguelike shooter starring Schiffy. Runs in the browser, nothing to install.

**Play:** https://aerynnnnn.github.io/schiffy-sky-patrol/

- WASD move, mouse aim and click to shoot, Space jump, Shift dash, right-click grenade, Q bark, E use, Tab upgrades, M map, Esc pause.
- Modes: Story (4 levels: Moonlit Meadows, Golden Reef, Frostcap Peaks, Ember Volcano), the Daily Challenge (open from the start), Endless and Boss Rush (open after clearing Level 1).
- Daily Challenge: one seeded run a day (UTC), the same isles and starting kit for everyone, scored by stages cleared.
- Schiffy's Home: the isle over the hub's east bridge. At its **Edit home** board you shop the home catalogue and arrange the isle: drag, stack, turn any way up and hover anything.
  - **Gold** (everyday furniture and garden): every coin you pick up in a run is also saved for the home.
  - **Paw Gems** (showpiece buildings): the premium currency (free playtest gems for now).
  - **Unlocks** (trophies): earned by milestones such as clearing each level, a Boss Rush, a 7-day Daily streak or finding every weapon.
  - 162 items in 12 sections (furniture, kitchen, lighting, garden, play, fences & paths, water, decor, seasonal, buildings, sky isles, trophies). **Preview** any item first: it stands on your isle at real size next to Schiffy, and you only pay when you press Buy & place.

## Models
The home catalogue's items are modelled in Blender by `blender/build_home.py`, which writes `home.glb` and each item's collision boxes; `blender/render_home.py` renders a preview of every item. (The full game source lives in a separate private repo.)

This is a playtest build. Feedback welcome!

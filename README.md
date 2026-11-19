# ZZ Race

A single-file browser rebuild of **Survival Race**: drift on a hex arena where every tile you touch turns your color and drops away, jump and fly with fold-out wings, and knock rivals into the void.

**Play:** open `index.html` in a browser (or via GitHub Pages).

## Modes
- **Battle** – last car on the shrinking arena wins (30s, 8 cars)
- **Parkour** – grab the most stars from floating islands and balloons
- **Autoball** – push soccer, basketball and rugby balls into the goals
- **Practice** – drive, drift, jump and fly with no rivals

## Controls
- Steer: `←` `→` / `A` `D` (mobile: slide finger)
- Jump: `Space` / `W` / `↑` (mobile: tap)
- Fly: jump again in the air (mobile: double-tap)
- Pause: `Esc`

## Tech
- Everything (code + 3D models) is in `index.html`; Three.js loads from a CDN.
- Car and prop models were built procedurally in Blender — see `tools/build_models.py` (run with the `bpy` Python module).

# Changelog

## 1.3.0

- Gallery category **Mazes & Fills**: Jigsaw Spiral, Cretan Labyrinth, Ring Maze, Random Maze, Tight Maze, Drift Maze, Hilbert Fill, Fine Hilbert, and Peano Fill. Each is one continuous line that fills the disc.

## 1.2.1

- The table reconnects on its own after the Bluetooth link drops. The wait starts near 2 seconds, doubles, and stops at 60 seconds.
- A fresh advertisement for that table skips the rest of the wait. A command while it is disconnected asks for the same retry and shows a short message instead of a stack trace.
- After the next handshake, Power, the lamp, and playback are restored.
- Diagnostic **Connected** sensor and **Reconnect** button.

## 1.2.0

- The dashboard card finds the only Drift table by itself. In the visual editor you pick the device when there is more than one. No YAML.
- Buttons say what went wrong in a sentence, and they do not call a service without an entity or a device.
- Sparse gallery designs are gone: Hex Tiling, Diamond Ring, Nautilus, Silk Ripple, Ring Tide, Sisyphus Nautilus, Sierpinski, Sierpinski Eight, and Triangle Weave.

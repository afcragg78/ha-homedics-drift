# Changelog

## 1.1.0

- The table reconnects on its own after the Bluetooth link drops. The wait starts near 2 seconds, doubles, and stops at 60 seconds.
- A fresh advertisement for that table skips the rest of the wait. A command while it is disconnected asks for the same retry and shows a short message instead of a stack trace.
- After the next handshake, Power, the lamp, and playback are restored.
- Diagnostic **Connected** sensor and **Reconnect** button.

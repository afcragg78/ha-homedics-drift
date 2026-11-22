# Changelog

## 1.4.11

- Weather and Auto Weather again upload, then start Clean, then play, the same order that worked in 1.4.6 while a playlist was running. The integration no longer waits for the table to go idle, and it no longer sends play/pause before an upload. That command is a toggle and could resume the playlist instead of starting Clean.
- After sending Clean, the integration waits up to 20 seconds for the table to report the clean pattern, and resends the draw once if needed. If Clean still does not start, it logs a warning and plays the weather picture instead of waiting 20 minutes. Playing weather is confirmed the same way, with one retry.
- The 280-page weather cap, the 4-second settle after a large upload, trailing or missing page resends, the link wait, clear errors, and the Preferred Bluetooth Adapter option are unchanged.


## 1.4.10

- Before a pattern upload, the integration pauses the table with the same play/pause command the player already uses, then waits a few seconds for the ball to stop. A stored playlist that keeps drawing no longer blocks Weather or other uploads by waiting for the table to go idle on its own.
- The 4-second settle after a large upload, the trailing or missing page resend, the 280-page weather cap, and the Preferred Bluetooth Adapter option are unchanged.


## 1.4.9

- Pattern uploads wait until the table is idle before sending, up to 20 minutes when a clean is running and 15 minutes otherwise. A pattern is never uploaded while the ball is still moving.
- After a large upload (more than 150 pages), the integration pauses about four seconds so the table can settle before Clean or Play starts.
- If the table is slow to confirm a stored pattern, or reports missing pages, only the trailing or missing pages are resent, the same way as 1.4.5. The error is still a clear sentence.
- Weather drawings are capped at 280 pages. Longer paths are simplified while keeping the symbols and clearance, so a forecast upload stays in a size the table can store reliably.


## 1.4.8

- Configure has a Preferred Bluetooth Adapter option. Automatic (the default) leaves the radio choice to Home Assistant, the same as before. Pick a specific connectable adapter or proxy, such as a USB dongle, to always connect the table through that radio. If the chosen adapter cannot see the table, the connection fails with a clear error instead of silently using another scanner.

## 1.4.7

- Pattern uploads wait for the table to be connected and to finish its handshake, then retry if it is slow to confirm the pattern was stored. Larger drawings get a longer wait, up to a minute. The error is always a clear sentence, not a blank popup.

## 1.4.6

- Weather drawings no longer cut through the symbols. The fill and the ball's travel stay outside each outline, the path goes around the shapes, fog bands use whole waves, and the partly-cloudy ripples sit a little farther apart.

## 1.4.2

- Wind is four long wavy lines under the temperature, evenly spaced, each ending in a large round curl. The upper curls roll up and the bottom curl rolls down. A combined picture keeps the symbol on the left and puts three curled gusts on the right. The curls are about one and a half times the earlier size, and on a sunny gust picture the ball leaves along a ray instead of cutting across the sun.
- The pattern preview on the card is turned by the same weather rotation that is sent to the table, so the card matches the sand.

## 1.4.1

- More weather symbols: thunderstorm, partly cloudy, clear night, fog, wind, hot, cold, hail, sleet, heavy rain, and a weather alert. Wind at or above the threshold is the whole picture on a fair sky, and a run of gusts beside rain, snow, a storm, hail, sleet, fog, hot, cold, or an alert. Defaults are 15 mph / 25 km/h, 90°F / 32°C, 32°F / 0°C, and a 70% chance of heavy rain. An optional alert entity, left empty, stays off.
- A weather path no longer draws a full orbit each time it crosses the negative x-axis. Theta is unwrapped, the same way the other drawings already do, so the ball follows the picture.
- `draw_weather` takes an optional `condition`. A name such as `windy` or `rain_wind` draws that picture and skips the forecast rules. Leave it empty to use the daily forecast.

## 1.4.0

- Photo to Sand. `homedics_drift.draw_photo` turns a picture, or a prompt that makes one, into a single ball path: a swept subject, the outline drawn twice, and contour lines that flow around it and fill the table.
- A preview writes the digital twin PNG and does not move the ball. Confirm draws that preview. The twin is ported from Drifted's sand model, MIT, Copyright (c) 2026 Altimix LLC.
- An optional camera, off until you pick one in Configure, snapshots the table after a photo drawing and logs how well it matches the twin.

## 1.3.0

- Draw the day's forecast on the sand. **Draw Weather** and `homedics_drift.draw_weather` use a weather entity (National Weather Service, Met.no, OpenWeatherMap, or any other), and **Auto Weather** follows a finished design. The picture is Josh Lannin's Drifted weather design, MIT, Copyright (c) 2026 Altimix LLC.
- Stop after this design still pauses the sand. With Auto Weather on, the order is: the finished design pauses, the wipe runs, the weather picture plays, and that picture pauses.

## 1.2.2

- The Pattern, Playlist, Favorites, and Folder Pattern dropdowns in the card's Table section list their choices again. They opened as an empty strip before.

## 1.2.1

- The table reconnects on its own after the Bluetooth link drops. The wait starts near 2 seconds, doubles, and stops at 60 seconds.
- A fresh advertisement for that table skips the rest of the wait. A command while it is disconnected asks for the same retry and shows a short message instead of a stack trace.
- After the next handshake, Power, the lamp, and playback are restored.
- Diagnostic **Connected** sensor and **Reconnect** button.

## 1.2.0

- The dashboard card finds the only Drift table by itself. In the visual editor you pick the device when there is more than one. No YAML.
- Buttons say what went wrong in a sentence, and they do not call a service without an entity or a device.
- Sparse gallery designs are gone: Hex Tiling, Diamond Ring, Nautilus, Silk Ripple, Ring Tide, Sisyphus Nautilus, Sierpinski, Sierpinski Eight, and Triangle Weave.

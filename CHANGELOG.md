# Changelog

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

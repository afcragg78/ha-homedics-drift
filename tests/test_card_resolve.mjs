import assert from "node:assert/strict";
import { resolveDriftEntities } from "../custom_components/homedics_drift/www/drift-table-resolve.js";

const device = "drift-device";
const stem = "living_room_ks2206011280_62_00_a1_20_99_74";

function entry(extra = {}) {
  return { device_id: device, platform: "homedics_drift", ...extra };
}

const entities = {
  [`media_player.${stem}_player`]: entry({ translation_key: "player" }),
  [`switch.${stem}_power`]: entry({ translation_key: "power" }),
  [`light.${stem}_light`]: entry({ translation_key: "lamp" }),
  [`number.${stem}_speed`]: entry({ translation_key: "speed" }),
  [`button.${stem}_clean_sand`]: entry({ translation_key: "clean_sand" }),
  [`select.${stem}_gallery_design`]: entry({ translation_key: "gallery" }),
  [`select.${stem}_pattern`]: entry({ translation_key: "pattern" }),
  [`sensor.${stem}_pattern_id`]: entry({ translation_key: "pattern" }),
  [`select.${stem}_favorites`]: entry({ translation_key: "favorites" }),
  [`select.${stem}_playlist`]: entry({ translation_key: "playlist" }),
  [`select.${stem}_folder_pattern`]: entry({ translation_key: "inbox" }),
  [`button.${stem}_upload_folder_pattern`]: entry({ translation_key: "upload_folder_pattern" }),
  [`text.${stem}_ai_prompt`]: entry({ translation_key: "ai_prompt" }),
  [`sensor.${stem}_pattern_slots`]: entry(),
  [`sensor.${stem}_now_playing`]: entry({ translation_key: "now_playing" }),
  "switch.living_room_drift_table_stop_after_this_design": entry({ translation_key: "stop_after" }),
  [`switch.${stem}_clean_before_pattern`]: entry({ translation_key: "clean_before" }),
  [`image.${stem}_now_playing_preview`]: entry({ translation_key: "preview" }),
  [`image.${stem}_gallery_preview`]: entry({ translation_key: "gallery_preview" }),
  "image.living_room_drift_table_drift_away": entry(),
  [`image.${stem}_lotus_mandala`]: entry({ translation_key: "gallery_tile" }),
  "light.other_room_lamp": { device_id: "other", platform: "hue", translation_key: "lamp" },
};

for (const value of Object.values(entities)) {
  assert.equal(value.unique_id, undefined);
}

const resolved = resolveDriftEntities(entities, {
  entity: `media_player.${stem}_player`,
});

assert.equal(resolved.deviceId, device);
assert.equal(resolved.found.player, `media_player.${stem}_player`);
assert.equal(resolved.found.power, `switch.${stem}_power`);
assert.equal(resolved.found.light, `light.${stem}_light`);
assert.equal(resolved.found.speed, `number.${stem}_speed`);
assert.equal(resolved.found.clean, `button.${stem}_clean_sand`);
assert.equal(resolved.found.gallery, `select.${stem}_gallery_design`);
assert.equal(resolved.found.stored, `select.${stem}_pattern`);
assert.notEqual(resolved.found.stored, `sensor.${stem}_pattern_id`);
assert.equal(resolved.found.favorites, `select.${stem}_favorites`);
assert.equal(resolved.found.playlist, `select.${stem}_playlist`);
assert.equal(resolved.found.inbox, `select.${stem}_folder_pattern`);
assert.equal(resolved.found.upload, `button.${stem}_upload_folder_pattern`);
assert.equal(resolved.found.prompt, `text.${stem}_ai_prompt`);
assert.equal(resolved.found.slots, `sensor.${stem}_pattern_slots`);
assert.equal(resolved.found.now, `sensor.${stem}_now_playing`);
assert.equal(resolved.found.stopAfter, "switch.living_room_drift_table_stop_after_this_design");
assert.equal(resolved.found.cleanBefore, `switch.${stem}_clean_before_pattern`);
assert.equal(resolved.found.preview, `image.${stem}_now_playing_preview`);
assert.deepEqual(resolved.tiles.sort(), [
  `image.${stem}_lotus_mandala`,
  "image.living_room_drift_table_drift_away",
].sort());

const missing = resolveDriftEntities(
  { "switch.kitchen_power": entry({ translation_key: "power" }) },
  { device },
);
assert.equal(missing.found.player, undefined);
assert.equal(missing.tiles.length, 0);

const bySuffix = resolveDriftEntities(
  {
    "select.table_playlist": entry(),
    "select.table_folder_pattern": entry(),
    "select.table_pattern": entry(),
    "sensor.table_pattern_id": entry({ translation_key: "pattern" }),
  },
  { device },
);
assert.equal(bySuffix.found.playlist, "select.table_playlist");
assert.equal(bySuffix.found.inbox, "select.table_folder_pattern");
assert.equal(bySuffix.found.stored, "select.table_pattern");

function table(stem, deviceId) {
  const row = (key) => ({ device_id: deviceId, platform: "homedics_drift", translation_key: key });
  return {
    [`media_player.${stem}_player`]: row("player"),
    [`switch.${stem}_power`]: row("power"),
    [`light.${stem}_light`]: row("lamp"),
    [`select.${stem}_playlist`]: row("playlist"),
    [`select.${stem}_pattern`]: row("pattern"),
    [`sensor.${stem}_pattern_id`]: row("pattern"),
  };
}

for (const stem of [
  "living_room_ks2206011280_62_00_a1_20_99_74",
  "living_room_drift_table",
  "ks2206011280",
]) {
  const picked = resolveDriftEntities(table(stem, `device-${stem}`), {});
  assert.equal(picked.deviceId, `device-${stem}`);
  assert.equal(picked.found.player, `media_player.${stem}_player`);
  assert.equal(picked.found.stored, `select.${stem}_pattern`);
  assert.equal(picked.notice, null);
}

const two = {
  ...table("living_room_drift_table", "one"),
  ...table("kitchen_drift_table", "two"),
};
const ambiguous = resolveDriftEntities(two, {});
assert.equal(ambiguous.deviceId, null);
assert.match(ambiguous.notice, /more than one Drift table/);

const empty = resolveDriftEntities({}, {});
assert.match(empty.notice, /Add your Drift table/);

// Match Drift entities from the frontend registry.
// hass.entities entries have translation_key, platform, and device_id.
// They do not include unique_id.

const ROLE_BY_KEY = {
  player: "player",
  lamp: "light",
  power: "power",
  speed: "speed",
  gallery: "gallery",
  preview: "preview",
  gallery_preview: "galleryPreview",
  clean_sand: "clean",
  draw_with_ai: "drawAi",
  favorite: "favorite",
  ai_prompt: "prompt",
  ai_job: "ai",
  slots: "slots",
  now_playing: "now",
  favorites: "favorites",
  stop_after: "stopAfter",
  clean_before: "cleanBefore",
  send_gallery: "send",
  random_gallery: "random",
  gallery_tile: "tile",
};

const ROLE_BY_SUFFIX = [
  ["_stop_after_this_design", "stopAfter"],
  ["_clean_before_pattern", "cleanBefore"],
  ["_now_playing_preview", "preview"],
  ["_gallery_preview", "galleryPreview"],
  ["_send_gallery_design", "send"],
  ["_gallery_design", "gallery"],
  ["_pattern_slots", "slots"],
  ["_now_playing", "now"],
  ["_ai_prompt", "prompt"],
  ["_ai_drawing", "ai"],
  ["_clean_sand", "clean"],
  ["_draw_with_ai", "drawAi"],
  ["_random_design", "random"],
  ["_favorites", "favorites"],
  ["_stop_after", "stopAfter"],
  ["_clean_before", "cleanBefore"],
  ["_player", "player"],
  ["_power", "power"],
  ["_light", "light"],
  ["_lamp", "light"],
  ["_speed", "speed"],
  ["_favorite", "favorite"],
  ["_preview", "preview"],
];

const PREVIEW_KEYS = new Set(["preview", "gallery_preview"]);

function roleFor(entityId, entry) {
  const key = entry && entry.translation_key;
  const id = String(entityId || "");
  if (key === "pattern" && id.startsWith("select.")) return "stored";
  if (key && ROLE_BY_KEY[key]) return ROLE_BY_KEY[key];
  const lower = id.toLowerCase();
  if (lower.startsWith("select.") && lower.endsWith("_pattern") && !lower.endsWith("_pattern_id")) {
    return "stored";
  }
  for (const [suffix, role] of ROLE_BY_SUFFIX) {
    if (lower.endsWith(suffix)) return role;
  }
  return null;
}

function isGalleryTile(entityId, entry, role) {
  if (!String(entityId).startsWith("image.")) return false;
  const key = entry && entry.translation_key;
  if (key === "gallery_tile") return true;
  if (PREVIEW_KEYS.has(key) || role === "preview" || role === "galleryPreview") return false;
  if (role) return false;
  return true;
}

export function resolveDriftEntities(entities, config) {
  const registry = entities || {};
  let deviceId = (config && (config.device || config.device_id)) || null;
  if (!deviceId && config && config.entity && registry[config.entity]) {
    deviceId = registry[config.entity].device_id || null;
  }
  const found = {};
  const tiles = [];
  Object.keys(registry).forEach((id) => {
    const entry = registry[id] || {};
    if (entry.platform && entry.platform !== "homedics_drift") return;
    if (deviceId && entry.device_id !== deviceId) return;
    const role = roleFor(id, entry);
    if (role && role !== "tile" && !found[role]) found[role] = id;
    if (isGalleryTile(id, entry, role)) tiles.push(id);
  });
  return { deviceId, found, tiles };
}

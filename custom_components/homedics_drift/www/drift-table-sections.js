// Which extra sections start open. The sand, transport, light switch,
// brightness, and speed stay on the card and are not in this list.

export const SECTION_IDS = ["more", "table", "gallery", "create", "color", "clean", "storage"];

const ALIASES = {
  more: "more",
  table: "table",
  gallery: "gallery",
  "my patterns": "gallery",
  create: "create",
  import: "create",
  color: "color",
  "light color": "color",
  clean: "clean",
  "clean sand": "clean",
  storage: "storage",
};

function names(value) {
  const raw = Array.isArray(value) ? value : String(value || "").split(/[\s,]+/);
  const found = [];
  raw.forEach((item) => {
    const key = ALIASES[String(item).trim().toLowerCase()];
    if (key && !found.includes(key)) found.push(key);
  });
  return found;
}

export function initialOpen(config, stored) {
  const collapsed = new Set(names(config && config.collapsed));
  const expanded = new Set(names(config && config.expanded));
  const open = {};
  SECTION_IDS.forEach((id) => {
    if (stored && typeof stored[id] === "boolean") open[id] = stored[id];
    else if (collapsed.has(id)) open[id] = false;
    else if (expanded.has(id)) open[id] = true;
    else open[id] = false;
  });
  const innerOpen = SECTION_IDS.some((id) => id !== "more" && open[id]);
  const moreStored = stored && typeof stored.more === "boolean";
  if (innerOpen && !moreStored && !collapsed.has("more")) open.more = true;
  return open;
}

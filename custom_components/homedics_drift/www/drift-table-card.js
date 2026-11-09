// Drift table card. Loaded by the integration; no separate frontend install.
// Theme colors come from Home Assistant CSS variables. Frosted glass is opt-in.
// Home Assistant elements are used when that frontend has registered them.

import { resolveDriftEntities } from "./drift-table-resolve.js";
import { initialOpen } from "./drift-table-sections.js";

const ICONS = {
  prev: "M6,18V6H8V18H6M9.5,12L18,6V18L9.5,12Z",
  play: "M8,5.14V19.14L19,12.14L8,5.14Z",
  pause: "M14,19H18V5H14M6,19H10V5H6V19Z",
  next: "M16,18H18V6H16M6,18L14.5,12L6,6V18Z",
  power: "M16.56,5.44L15.11,6.89C16.84,7.94 18,9.83 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12C6,9.83 7.16,7.94 8.88,6.88L7.44,5.44C5.36,6.88 4,9.28 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,9.28 18.64,6.88 16.56,5.44M13,3H11V13H13",
  stop: "M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M9,9H11V15H9V9M13,9H15V15H13V9Z",
  clean: "M19.36,2.72L20.78,4.14L15.06,9.85C16.13,11.39 16.28,13.24 15.38,14.44L9.06,8.12C10.26,7.22 12.11,7.37 13.65,8.44L19.36,2.72M5.93,17.57C3.92,15.56 2.69,13.16 2.35,10.92L7.23,8.83L14.67,16.27L12.58,21.15C10.34,20.81 7.94,19.58 5.93,17.57Z",
  chevron: "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z",
};

const SWATCHES = [
  ["Warm", [255, 176, 96]],
  ["White", [255, 255, 255]],
  ["Amber", [255, 140, 0]],
  ["Rose", [255, 96, 128]],
  ["Green", [80, 200, 120]],
  ["Blue", [80, 140, 255]],
];

function hasElement(name) {
  return Boolean(customElements.get(name));
}

function setDisabled(el, disabled) {
  if (!el) return;
  el.disabled = Boolean(disabled);
  if (disabled) el.setAttribute("disabled", "");
  else el.removeAttribute("disabled");
}

function iconButton(label, path) {
  if (hasElement("ha-icon-button")) {
    const el = document.createElement("ha-icon-button");
    el.label = label;
    el.path = path;
    return el;
  }
  const el = document.createElement("button");
  el.type = "button";
  el.className = "icon";
  el.setAttribute("aria-label", label);
  el.title = label;
  el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"></path></svg>`;
  return el;
}

function setIcon(el, path) {
  if (el.tagName === "HA-ICON-BUTTON") el.path = path;
  const node = el.querySelector("path");
  if (node) node.setAttribute("d", path);
}

function setSelected(el, on) {
  el.selected = Boolean(on);
  el.classList.toggle("on", Boolean(on));
  if (on) el.setAttribute("selected", "");
  else el.removeAttribute("selected");
}

class DriftTableCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getConfigForm() {
    const flag = (name, label) => ({ name, selector: { boolean: {} }, helper: label });
    return {
      schema: [
        {
          name: "device",
          selector: { device: {} },
          helper: "Pick the Drift device. With one table this can stay empty.",
        },
        { name: "entity", selector: { entity: {} } },
        {
          name: "style",
          selector: {
            select: {
              options: [
                { value: "native", label: "Native" },
                { value: "frosted", label: "Frosted" },
                { value: "minimal", label: "Minimal" },
              ],
              mode: "dropdown",
            },
          },
        },
        flag("show_now", "Now Playing"),
        flag("show_table", "Table"),
        flag("show_gallery", "Gallery"),
        flag("show_create", "Create"),
        flag("show_light", "Light"),
        flag("show_speed", "Speed"),
        flag("show_clean", "Clean Sand"),
        flag("show_storage", "Storage"),
        {
          name: "expanded",
          selector: { text: {} },
          helper: "Sections that start open: more, table, gallery, create, color, clean, storage",
        },
        {
          name: "collapsed",
          selector: { text: {} },
          helper: "Sections forced closed. Same names as expanded.",
        },
      ],
    };
  }

  setConfig(config) {
    this._config = config || {};
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) this._config = {};
    this._ensure();
    this._update();
  }

  getCardSize() {
    return 6;
  }

  _shown(key) {
    return this._config[key] !== false;
  }

  _styleName() {
    const style = this._config.style || "native";
    return style === "frosted" || style === "minimal" ? style : "native";
  }

  _resolve() {
    const hass = this._hass;
    return resolveDriftEntities((hass && hass.entities) || {}, this._config || {});
  }

  _storageKey() {
    const id = (this._config && (this._config.entity || this._config.device || this._config.device_id)) || "drift";
    return `drift-table-card:${id}`;
  }

  _loadOpen() {
    let stored = null;
    try {
      stored = JSON.parse(localStorage.getItem(this._storageKey()) || "null");
    } catch (_err) {
      stored = null;
    }
    if (!stored || typeof stored !== "object") stored = null;
    this._open = initialOpen(this._config, stored);
  }

  _remember(id, expanded) {
    this._open[id] = Boolean(expanded);
    try {
      localStorage.setItem(this._storageKey(), JSON.stringify(this._open));
    } catch (_err) {
      /* private mode */
    }
  }

  _call(domain, service, data) {
    if (!this._hass || !data) return;
    if (!data.entity_id && !data.device_id) {
      this._say("That control is not on this table yet.");
      return;
    }
    const pending = this._hass.callService(domain, service, data);
    if (pending && typeof pending.catch === "function") {
      pending.catch((err) => this._say(this._friendly(err)));
    }
  }

  _friendly(err) {
    const raw = String((err && err.message) || err || "");
    if (/not connected|reconnect/i.test(raw)) return "The table is not connected. It will try again on its own.";
    if (/power is off/i.test(raw)) return "Turn Power on before drawing.";
    if (!raw || raw.length > 160 || /Error|Exception|Traceback|object has no attribute/i.test(raw)) {
      return "That did not work. Check that the table is on and in range.";
    }
    return raw;
  }

  _say(text) {
    this._toast = text;
    const note = this._card && this._card.querySelector(".missing");
    if (note) {
      note.hidden = false;
      note.textContent = text;
    }
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      if (this._hass) this._update();
    }, 6000);
  }

  _action(label) {
    if (hasElement("ha-button")) {
      const el = document.createElement("ha-button");
      el.setAttribute("appearance", "plain");
      el.setAttribute("variant", "brand");
      el.textContent = label;
      return el;
    }
    const el = document.createElement("button");
    el.type = "button";
    el.className = "plain";
    el.textContent = label;
    return el;
  }

  _switch() {
    if (hasElement("ha-switch")) {
      const el = document.createElement("ha-switch");
      el.setAttribute("aria-label", "Light");
      return el;
    }
    const el = document.createElement("button");
    el.type = "button";
    el.className = "switch";
    el.setAttribute("role", "switch");
    el.setAttribute("aria-label", "Light");
    el.setAttribute("aria-checked", "false");
    return el;
  }

  _slider(label, min, max, unit) {
    const tag = hasElement("ha-control-slider") ? "ha-control-slider" : hasElement("ha-slider") ? "ha-slider" : "";
    if (tag) {
      const el = document.createElement(tag);
      el.label = label;
      el.min = min;
      el.max = max;
      el.step = 1;
      if (unit) el.unit = unit;
      return el;
    }
    const el = document.createElement("input");
    el.type = "range";
    el.className = "slider";
    el.min = String(min);
    el.max = String(max);
    el.step = "1";
    el.setAttribute("aria-label", label);
    return el;
  }

  _select(label) {
    if (hasElement("ha-select")) {
      const el = document.createElement("ha-select");
      el.label = label;
      return el;
    }
    const el = document.createElement("select");
    el.setAttribute("aria-label", label);
    return el;
  }

  _textControl(label, { multiline, className, placeholder }) {
    if (!multiline && hasElement("ha-textfield")) {
      const el = document.createElement("ha-textfield");
      el.label = label;
      el.placeholder = placeholder || "";
      el.className = className;
      return el;
    }
    if (!multiline && hasElement("ha-input")) {
      const el = document.createElement("ha-input");
      el.label = label;
      el.placeholder = placeholder || "";
      el.className = className;
      return el;
    }
    const el = document.createElement(multiline ? "textarea" : "input");
    if (!multiline) el.type = "url";
    el.className = className;
    el.placeholder = placeholder || "";
    el.setAttribute("aria-label", label);
    return el;
  }

  _panel(id, title) {
    const open = Boolean(this._open[id]);
    if (hasElement("ha-expansion-panel")) {
      const panel = document.createElement("ha-expansion-panel");
      panel.header = title;
      panel.expanded = open;
      panel.dataset.section = id;
      panel.addEventListener("expanded-changed", (event) => {
        const expanded = Boolean(event.detail && event.detail.expanded);
        this._remember(id, expanded);
      });
      return panel;
    }
    const panel = document.createElement("section");
    panel.className = "panel";
    panel.dataset.section = id;
    const head = document.createElement("button");
    head.type = "button";
    head.className = "panel-head";
    head.setAttribute("aria-expanded", open ? "true" : "false");
    const label = document.createElement("span");
    label.textContent = title;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", ICONS.chevron);
    svg.appendChild(path);
    head.append(label, svg);
    const body = document.createElement("div");
    body.className = "panel-body";
    body.hidden = !open;
    head.addEventListener("click", () => {
      const next = body.hidden;
      body.hidden = !next;
      head.setAttribute("aria-expanded", next ? "true" : "false");
      this._remember(id, next);
    });
    panel.append(head, body);
    return panel;
  }

  _place(panel) {
    return panel.querySelector(":scope > .panel-body") || panel;
  }

  _wireSlider(el, apply) {
    const read = (event) => {
      const detail = event.detail && event.detail.value;
      const raw = detail !== undefined ? detail : event.target.value;
      this._drag = null;
      apply(raw);
    };
    el.addEventListener("slider-moved", () => {
      this._drag = el;
    });
    if (el.tagName === "HA-CONTROL-SLIDER" || el.tagName === "HA-SLIDER") {
      el.addEventListener("value-changed", read);
    } else {
      el.addEventListener("change", read);
    }
  }

  _ensure() {
    const style = this._styleName();
    if (this._built && this._styleApplied === style) return;
    this._styleApplied = style;
    this._built = true;
    this._points = null;
    this._pathFor = null;
    this._shownProgress = null;
    this._drag = null;
    this._loadOpen();
    const card = document.createElement("ha-card");
    card.className = "drift-table" + (style === "native" ? "" : " " + style);
    card.innerHTML = `
      <style>
        :host { display: block; }
        ha-card.drift-table { color: var(--primary-text-color); border-radius: var(--ha-card-border-radius, 12px); overflow: hidden; }
        ha-card.drift-table.frosted { --ha-card-background: color-mix(in srgb, var(--card-background-color, var(--ha-card-background, #fff)) 62%, transparent); backdrop-filter: blur(18px); border: 1px solid var(--divider-color); }
        ha-card.drift-table.minimal { --ha-card-background: transparent; --ha-card-box-shadow: none; box-shadow: none; }
        .body { padding: 12px 12px 4px; display: flex; flex-direction: column; gap: 4px; }
        h2 { margin: 12px 0 4px; font-size: 1rem; font-weight: 500; color: var(--primary-text-color); }
        .missing { margin: 0 0 8px; color: var(--primary-text-color); }
        .stage { position: relative; width: min(100%, 240px); margin: 0 auto; aspect-ratio: 1; }
        .ring { position: absolute; inset: 0; width: 100%; height: 100%; }
        .ring circle.track { fill: none; stroke: var(--divider-color); stroke-width: 6; }
        .ring circle.value { fill: none; stroke: var(--primary-color); stroke-width: 6; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 50% 50%; }
        .sand { position: absolute; inset: 11%; border-radius: 50%; overflow: hidden; background: #e4c79a; box-shadow: 0 0 0 2px var(--glow, var(--divider-color)), 0 0 22px 2px var(--glow, transparent); }
        canvas, .still { width: 100%; height: 100%; display: block; object-fit: cover; }
        .still[hidden], canvas[hidden] { display: none; }
        .name { text-align: center; margin: 6px 0 0; font-size: 1.05rem; }
        .transport { display: flex; justify-content: center; align-items: center; }
        button, ha-button {
          background: transparent; color: var(--primary-text-color); border: none; border-radius: 0;
          box-shadow: none; padding: 8px; font: inherit; font-weight: 500; cursor: pointer;
          --ha-button-border-radius: 0; --ha-button-box-shadow: none;
        }
        button.plain, ha-button { color: var(--primary-color); font-weight: 600; }
        button.icon {
          width: 40px; height: 40px; padding: 0; border-radius: 50%;
          display: inline-flex; align-items: center; justify-content: center;
        }
        button.icon svg, .panel-head svg { width: 24px; height: 24px; fill: currentColor; }
        button.icon.on, button.icon[selected], ha-icon-button[selected] { color: var(--primary-color); }
        button:disabled, ha-button[disabled], ha-icon-button[disabled], button.icon:disabled { color: var(--disabled-text-color); cursor: default; }
        button.icon:hover, .panel-head:hover { background: var(--secondary-background-color); }
        ha-icon-button { color: var(--primary-text-color); --ha-icon-button-size: 40px; }
        .line { display: flex; align-items: center; justify-content: space-between; min-height: 40px; gap: 8px; }
        .line span { font-weight: 500; }
        .light-row, .speed-row { --control-slider-thickness: 32px; }
        input.slider { width: 100%; accent-color: var(--primary-color); }
        button.switch { width: 40px; height: 24px; border-radius: 12px; padding: 0; background: var(--divider-color); position: relative; }
        button.switch::after { content: ""; position: absolute; width: 18px; height: 18px; border-radius: 50%; background: var(--card-background-color, #fff); top: 3px; left: 3px; }
        button.switch[aria-checked="true"] { background: var(--primary-color); }
        button.switch[aria-checked="true"]::after { left: 19px; }
        .panel-head { display: flex; align-items: center; width: 100%; min-height: 48px; padding: 0 8px; text-align: left; }
        .panel-head span { flex: 1; }
        .panel-head[aria-expanded="true"] svg { transform: rotate(180deg); }
        .panel-body { padding: 0 8px 8px; }
        .choice { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
        .choice-label { width: 7rem; flex: none; font-weight: 500; }
        .choice ha-select, .choice select { flex: 1; min-width: 0; width: 100%; font: inherit; color: var(--primary-text-color); background: transparent; border: none; border-bottom: 1px solid var(--divider-color); border-radius: 0; padding: 8px 0; }
        .tabs { display: flex; gap: 4px; overflow-x: auto; margin-bottom: 8px; }
        .tabs button { white-space: nowrap; color: var(--secondary-text-color); background: transparent; }
        .tabs button.active { color: var(--primary-color); box-shadow: inset 0 -2px 0 var(--primary-color); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 8px; max-height: 280px; overflow: auto; }
        .grid button { padding: 0; border-radius: var(--ha-card-border-radius, 8px); overflow: hidden; }
        .grid button.picked { outline: 2px solid var(--primary-color); }
        .grid img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; background: var(--secondary-background-color); }
        .pick { display: flex; align-items: center; gap: 4px; margin-top: 8px; }
        .pick .label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        textarea.prompt, input.import-url {
          width: 100%; box-sizing: border-box; font: inherit; color: var(--primary-text-color);
          background: transparent; border: none; border-bottom: 1px solid var(--divider-color); border-radius: 0; padding: 8px 0;
        }
        textarea.prompt { min-height: 72px; resize: vertical; }
        .import-status, .status { margin-top: 6px; color: var(--secondary-text-color); min-height: 1.2em; }
        .bar { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; margin-top: 8px; }
        .bar span { display: block; height: 100%; width: 0; background: var(--primary-color); }
        .swatches { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
        .swatches button { width: 32px; height: 32px; min-height: 32px; border-radius: 50%; border: 1px solid var(--divider-color); padding: 0; }
        .meter { display: flex; align-items: center; gap: 8px; }
        .meter .bar { flex: 1; margin: 0; }
        .clean-row { display: flex; align-items: center; }
        @media (max-width: 520px) { .body { padding: 12px 12px 4px; } .stage { width: min(100%, 220px); } }
      </style>
      <div class="body">
        <p class="missing" hidden>This card could not find the Drift player. Set the card to that media player, or to the Drift device.</p>
        <section class="basics">
          <div class="stage-wrap">
            <div class="stage">
              <svg class="ring" viewBox="0 0 100 100" aria-hidden="true"><circle class="track" cx="50" cy="50" r="46"></circle><circle class="value" cx="50" cy="50" r="46"></circle></svg>
              <div class="sand"><canvas width="320" height="320"></canvas><img class="still" alt="" hidden></div>
            </div>
            <div class="name"></div>
          </div>
          <div class="row transport"></div>
          <div class="light-row"><div class="line"><span>Light</span></div></div>
          <div class="speed-row"><div class="line"><span>Speed</span></div></div>
        </section>
        <div class="more-host"></div>
      </div>`;
    this._buildControls(card);
    this.shadowRoot.replaceChildren(card);
    this._card = card;
    this._canvas = card.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
    this._bind(card);
  }

  _buildControls(card) {
    const transport = card.querySelector(".transport");
    [
      ["prev", "Prev", ICONS.prev],
      ["play", "Play", ICONS.play],
      ["next", "Next", ICONS.next],
      ["power", "Power", ICONS.power],
      ["stop-after", "Stop After", ICONS.stop],
    ].forEach(([act, label, path]) => {
      const button = iconButton(label, path);
      button.dataset.role = act;
      button.dataset.act = act;
      transport.appendChild(button);
    });
    this._lightSwitch = this._switch();
    card.querySelector(".light-row .line").appendChild(this._lightSwitch);
    this._bright = this._slider("Brightness", 1, 255);
    card.querySelector(".light-row").appendChild(this._bright);
    this._speedSlider = this._slider("Speed", 0, 100, "%");
    card.querySelector(".speed-row").appendChild(this._speedSlider);

    const more = this._panel("more", "More");
    const moreBody = this._place(more);
    moreBody.append(
      this._tablePanel(),
      this._galleryPanel(),
      this._createPanel(),
      this._colorPanel(),
      this._cleanPanel(),
      this._storagePanel(),
    );
    card.querySelector(".more-host").appendChild(more);
  }

  _tablePanel() {
    const panel = this._panel("table", "Table");
    const body = this._place(panel);
    [
      ["stored", "Pattern", true],
      ["playlist", "Playlist", true],
      ["favorites", "Favorites", true],
      ["inbox", "Folder Pattern", false],
    ].forEach(([role, label, plays]) => {
      const row = document.createElement("div");
      row.className = "choice";
      row.dataset.choice = role;
      const name = document.createElement("span");
      name.className = "choice-label";
      name.textContent = label;
      const select = this._select(label);
      row.append(select);
      if (!hasElement("ha-select")) row.insertBefore(name, select);
      if (plays) {
        const play = this._action("Play");
        play.classList.add("play");
        row.appendChild(play);
      } else {
        const upload = this._action("Upload");
        upload.classList.add("upload");
        row.appendChild(upload);
      }
      body.appendChild(row);
    });
    return panel;
  }

  _galleryPanel() {
    const panel = this._panel("gallery", "Gallery");
    const body = this._place(panel);
    const wrap = document.createElement("div");
    wrap.innerHTML = '<div class="tabs"></div><div class="grid"></div><div class="pick"><span class="label"></span></div>';
    const heart = this._action("Favorite");
    heart.classList.add("heart");
    const draw = this._action("Draw");
    draw.classList.add("draw");
    wrap.querySelector(".pick").append(heart, draw);
    body.appendChild(wrap);
    return panel;
  }

  _createPanel() {
    const panel = this._panel("create", "Create");
    const body = this._place(panel);
    const prompt = this._textControl("AI Prompt", {
      multiline: true,
      className: "prompt",
      placeholder: "A twelve pointed star",
    });
    const ai = this._action("Draw With AI");
    ai.classList.add("ai");
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.innerHTML = '<span class="ai-bar"></span>';
    const status = document.createElement("div");
    status.className = "status";
    const heading = document.createElement("h2");
    heading.textContent = "Import";
    const url = this._textControl("Pattern Link", {
      className: "import-url",
      placeholder: "https://… .thr or .gcode",
    });
    const button = this._action("Import");
    button.classList.add("import");
    const note = document.createElement("div");
    note.className = "import-status";
    body.append(prompt, ai, bar, status, heading, url, button, note);
    return panel;
  }

  _colorPanel() {
    const panel = this._panel("color", "Light Color");
    const body = this._place(panel);
    const row = document.createElement("div");
    row.className = "swatches";
    SWATCHES.forEach(([name, rgb]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "swatch";
      button.dataset.rgb = rgb.join(",");
      button.setAttribute("aria-label", name);
      button.title = name;
      button.style.background = `rgb(${rgb.join(",")})`;
      row.appendChild(button);
    });
    const more = this._action("More Colors");
    more.classList.add("more-colors");
    body.append(row, more);
    return panel;
  }

  _cleanPanel() {
    const panel = this._panel("clean", "Clean Sand");
    const row = document.createElement("div");
    row.className = "clean-row";
    const icon = iconButton("Clean Sand", ICONS.clean);
    icon.classList.add("clean");
    const label = this._action("Clean Sand");
    label.classList.add("clean");
    row.append(icon, label);
    this._place(panel).appendChild(row);
    return panel;
  }

  _storagePanel() {
    const panel = this._panel("storage", "Storage");
    const meter = document.createElement("div");
    meter.className = "meter";
    meter.innerHTML = '<span class="slots"></span><div class="bar"><span class="slot-bar"></span></div>';
    this._place(panel).appendChild(meter);
    return panel;
  }

  _bind(card) {
    card.querySelector(".transport").addEventListener("click", (event) => {
      const button = event.target.closest("ha-icon-button, button");
      if (!button || button.disabled) return;
      const id = this._found.player;
      const map = { prev: "media_previous_track", play: "media_play", pause: "media_pause", next: "media_next_track" };
      if (button.dataset.act === "power") {
        const on = this._state(this._found.power) === "on";
        this._call("switch", on ? "turn_off" : "turn_on", { entity_id: this._found.power });
        return;
      }
      if (button.dataset.role === "stop-after") {
        const on = this._state(this._found.stopAfter) === "on";
        this._call("switch", on ? "turn_off" : "turn_on", { entity_id: this._found.stopAfter });
        return;
      }
      const service = map[button.dataset.act];
      if (service && id) this._call("media_player", service, { entity_id: id });
    });
    this._lightSwitch.addEventListener("change", () => {
      if (this._lightSwitch.tagName !== "HA-SWITCH") return;
      this._toggleLight();
    });
    this._lightSwitch.addEventListener("click", () => {
      if (this._lightSwitch.tagName === "HA-SWITCH" || this._lightSwitch.disabled) return;
      const next = this._lightSwitch.getAttribute("aria-checked") !== "true";
      this._lightSwitch.setAttribute("aria-checked", next ? "true" : "false");
      this._toggleLight();
    });
    this._wireSlider(this._bright, (value) => {
      if (!this._found.light) return;
      const brightness = Math.max(1, Math.min(255, Math.round(Number(value))));
      this._call("light", "turn_on", { entity_id: this._found.light, brightness });
    });
    this._wireSlider(this._speedSlider, (value) => {
      if (!this._found.speed) return;
      this._call("number", "set_value", { entity_id: this._found.speed, value: Math.round(Number(value)) });
    });
    card.querySelectorAll(".choice").forEach((row) => {
      const select = row.querySelector("ha-select, select");
      const role = row.dataset.choice;
      const send = () => {
        const option = select.value;
        const entity = this._found[role];
        if (!option || !entity) return;
        if (role !== "inbox" && this._state(this._found.power) !== "on") return;
        this._call("select", "select_option", { entity_id: entity, option });
      };
      if (select.tagName === "HA-SELECT") {
        select.addEventListener("selected", (event) => {
          const option = event.detail && event.detail.value;
          if (option) select.value = option;
          send();
        });
      } else {
        select.addEventListener("change", send);
      }
      const play = row.querySelector(".play");
      if (play) play.addEventListener("click", send);
      const upload = row.querySelector(".upload");
      if (upload) {
        upload.addEventListener("click", () => {
          if (this._found.upload) this._call("button", "press", { entity_id: this._found.upload });
        });
      }
    });
    card.querySelector(".draw").addEventListener("click", () => {
      const name = this._picked;
      if (!name || !this._deviceId) return;
      if (this._state(this._found.power) !== "on") return;
      if (this._category === "My Patterns") {
        this._call("select", "select_option", { entity_id: this._found.stored, option: name });
        return;
      }
      if (this._found.gallery) this._call("select", "select_option", { entity_id: this._found.gallery, option: name });
      this._call("homedics_drift", "add_gallery_design", { device_id: this._deviceId, name, play: true });
    });
    card.querySelector(".heart").addEventListener("click", () => {
      const name = this._picked;
      if (!name || !this._deviceId) return;
      const on = (this._favorites || []).includes(name);
      this._call("homedics_drift", "set_favorite", { device_id: this._deviceId, name, favorite: !on });
    });
    card.querySelector(".import").addEventListener("click", () => {
      const field = card.querySelector(".import-url");
      const url = (field.value || "").trim();
      const note = card.querySelector(".import-status");
      if (!url || !this._deviceId || !this._hass) {
        note.textContent = "Paste a .thr or .gcode link first.";
        return;
      }
      note.textContent = "Importing…";
      this._hass
        .callService("homedics_drift", "import_pattern_url", { device_id: this._deviceId, url }, undefined, true)
        .then((result) => {
          const body = (result && (result.response || result)) || {};
          const stored = Number(body.stored || 0);
          const skipped = body.skipped || [];
          note.textContent = skipped.length
            ? `Stored ${stored}. Skipped: ${skipped.join(", ")}`
            : `Stored ${stored}.`;
          this._mineDevice = this._deviceId;
          this._loadMine();
        })
        .catch((err) => {
          const text = this._friendly(err);
          note.textContent = text;
          this._say(text === "That did not work. Check that the table is on and in range." ? "That link could not be imported." : text);
        });
    });
    card.querySelector(".ai").addEventListener("click", () => {
      const text = (card.querySelector(".prompt").value || "").trim();
      if (!text || !this._deviceId) return;
      if (this._found.prompt) this._call("text", "set_value", { entity_id: this._found.prompt, value: text });
      const powerOn = this._state(this._found.power) === "on";
      this._call("homedics_drift", "ai_draw", { device_id: this._deviceId, prompt: text, play: powerOn });
    });
    card.querySelector(".clean-row").addEventListener("click", (event) => {
      if (!event.target.closest(".clean") || !this._found.clean) return;
      if (this._state(this._found.power) !== "on") return;
      this._call("button", "press", { entity_id: this._found.clean });
    });
    card.querySelector(".swatches").addEventListener("click", (event) => {
      const button = event.target.closest(".swatch");
      if (!button || !this._found.light || this._state(this._found.power) !== "on") return;
      const rgb = button.dataset.rgb.split(",").map((part) => Number(part));
      this._call("light", "turn_on", { entity_id: this._found.light, rgb_color: rgb });
    });
    card.querySelector(".more-colors").addEventListener("click", () => {
      if (!this._found.light) return;
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId: this._found.light },
        bubbles: true,
        composed: true,
      }));
    });
    card.querySelector(".tabs").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      this._category = button.dataset.cat;
      if (this._category === "My Patterns") {
        const names = (this._mine || []).map((item) => item.name);
        if (!names.includes(this._picked)) this._picked = names[0] || "";
      }
      card.querySelector(".tabs").dataset.key = "";
      card.querySelector(".grid").dataset.key = "";
      this._updateGallery();
    });
    card.querySelector(".grid").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !button.dataset.name) return;
      this._picked = button.dataset.name;
      if (this._category !== "My Patterns" && this._found.gallery) {
        this._call("select", "select_option", { entity_id: this._found.gallery, option: this._picked });
      }
      this._renderGrid();
      card.querySelector(".pick .label").textContent = this._picked;
    });
  }

  _toggleLight() {
    if (!this._found.light || this._state(this._found.power) !== "on") return;
    const on = this._lightSwitch.tagName === "HA-SWITCH"
      ? Boolean(this._lightSwitch.checked)
      : this._lightSwitch.getAttribute("aria-checked") === "true";
    this._call("light", on ? "turn_on" : "turn_off", { entity_id: this._found.light });
  }

  _state(id) {
    if (!id || !this._hass || !this._hass.states[id]) return undefined;
    return this._hass.states[id].state;
  }

  _attr(id, key) {
    const state = id && this._hass && this._hass.states[id];
    return state && state.attributes ? state.attributes[key] : undefined;
  }

  _update() {
    const resolved = this._resolve();
    this._found = resolved.found;
    this._deviceId = resolved.deviceId;
    this._tiles = resolved.tiles;
    const card = this._card;
    const missing = card.querySelector(".missing");
    if (missing) {
      if (this._toast) {
        missing.hidden = false;
        missing.textContent = this._toast;
      } else if (resolved.notice) {
        missing.hidden = false;
        missing.textContent = resolved.notice;
      } else {
        missing.hidden = true;
      }
    }
    card.querySelector(".stage-wrap").hidden = !this._shown("show_now");
    card.querySelector(".light-row").hidden = !this._shown("show_light");
    card.querySelector(".speed-row").hidden = !this._shown("show_speed");
    const show = {
      table: this._shown("show_table"),
      gallery: this._shown("show_gallery"),
      create: this._shown("show_create"),
      color: this._shown("show_light"),
      clean: this._shown("show_clean"),
      storage: this._shown("show_storage"),
    };
    Object.keys(show).forEach((id) => {
      const panel = card.querySelector(`[data-section="${id}"]`);
      if (panel) panel.hidden = !show[id];
    });
    const more = card.querySelector('[data-section="more"]');
    if (more) more.hidden = !Object.values(show).some(Boolean);
    this._updateNow();
    this._updateLight();
    this._updateTable();
    this._updateGallery();
    this._updateCreate();
    this._updateFoot();
  }

  _updateNow() {
    const now = this._found.now;
    const name = this._state(now);
    this._card.querySelector(".name").textContent = name && name !== "unknown" ? name : "Idle";
    const progress = Number(this._attr(now, "progress"));
    const target = Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0;
    this._seek(target);
    const rgb = this._attr(this._found.light, "rgb_color");
    const glow = Array.isArray(rgb) ? `rgb(${rgb.join(",")})` : "var(--divider-color)";
    this._card.querySelector(".sand").style.setProperty("--glow", this._state(this._found.light) === "on" ? glow : "var(--divider-color)");
    const powerOn = this._state(this._found.power) === "on";
    const playing = this._state(this._found.player) === "playing";
    this._card.querySelectorAll(".transport ha-icon-button, .transport button").forEach((button) => {
      if (button.dataset.role === "power") {
        setSelected(button, powerOn);
        button.label = powerOn ? "Power On" : "Power Off";
        button.setAttribute("aria-label", button.label);
        if (button.title !== undefined) button.title = button.label;
        setDisabled(button, !this._found.power);
        return;
      }
      if (button.dataset.role === "stop-after") {
        const held = this._state(this._found.stopAfter) === "on";
        setSelected(button, held);
        button.label = held ? "Stop After On" : "Stop After";
        button.setAttribute("aria-label", button.label);
        if (button.title !== undefined) button.title = button.label;
        setDisabled(button, !this._found.stopAfter);
        return;
      }
      if (button.dataset.role === "play") {
        button.dataset.act = playing ? "pause" : "play";
        button.label = playing ? "Pause" : "Play";
        button.setAttribute("aria-label", button.label);
        if (button.title !== undefined) button.title = button.label;
        setIcon(button, playing ? ICONS.pause : ICONS.play);
      }
      setDisabled(button, !powerOn || !this._found.player);
    });
    const patternId = Number(this._attr(now, "pattern_id") || 0);
    const known = this._attr(now, "path_known") === true;
    const picture = this._attr(this._found.preview, "entity_picture");
    const still = this._card.querySelector(".still");
    if (!known || patternId <= 0) {
      this._points = null;
      this._pathFor = null;
      still.hidden = !picture;
      this._canvas.hidden = !!picture;
      if (picture) still.src = picture;
      else this._paint(null, this._shownProgress || 0);
      return;
    }
    still.hidden = true;
    this._canvas.hidden = false;
    if (this._pathFor !== patternId) {
      this._pathFor = patternId;
      this._points = null;
      this._loadPath(patternId);
    } else {
      this._paint(this._points, this._shownProgress || 0);
    }
  }

  _updateLight() {
    const on = this._state(this._found.light) === "on";
    const powerOn = this._state(this._found.power) === "on";
    if (this._lightSwitch.tagName === "HA-SWITCH") this._lightSwitch.checked = on;
    else this._lightSwitch.setAttribute("aria-checked", on ? "true" : "false");
    setDisabled(this._lightSwitch, !powerOn || !this._found.light);
    setDisabled(this._bright, !powerOn || !this._found.light);
    if (this._drag !== this._bright) {
      const level = this._attr(this._found.light, "brightness");
      if (level != null) this._bright.value = level;
    }
    if (this._drag !== this._speedSlider && this._state(this._found.speed) != null && this._state(this._found.speed) !== "unknown") {
      this._speedSlider.value = this._state(this._found.speed);
    }
    const locked = !powerOn || !this._found.light;
    this._card.querySelectorAll(".swatch, .more-colors").forEach((el) => setDisabled(el, locked));
  }

  _fillSelect(select, options, value) {
    const list = options || [];
    const key = list.join("\n");
    if (select.dataset.key !== key) {
      select.dataset.key = key;
      if (select.tagName === "HA-SELECT") select.options = list;
      else {
        select.replaceChildren();
        list.forEach((name) => {
          const option = document.createElement("option");
          option.value = name;
          option.textContent = name;
          select.appendChild(option);
        });
      }
    }
    if (document.activeElement === select) return;
    const next = value || "";
    if (select.value !== next) select.value = next;
  }

  _updateTable() {
    const powerOn = this._state(this._found.power) === "on";
    this._card.querySelectorAll(".choice").forEach((row) => {
      const role = row.dataset.choice;
      const id = this._found[role];
      row.hidden = !id;
      if (!id) return;
      const select = row.querySelector("ha-select, select");
      const rawOptions = this._attr(id, "options");
      const options = Array.isArray(rawOptions) ? rawOptions : [];
      const current = this._state(id);
      this._fillSelect(select, options, options.includes(current) ? current : "");
      const play = row.querySelector(".play");
      if (play) setDisabled(play, !powerOn || !select.value);
      const upload = row.querySelector(".upload");
      if (upload) {
        upload.hidden = !this._found.upload;
        setDisabled(upload, !this._found.upload);
      }
    });
  }

  async _loadPath(patternId) {
    if (!this._hass || !this._deviceId) return;
    try {
      const data = await this._hass.callApi("GET", `homedics_drift/path/${encodeURIComponent(this._deviceId)}`);
      if (this._pathFor !== patternId) return;
      this._points = data && Array.isArray(data.points) && data.points.length > 1 ? data.points : null;
    } catch (_err) {
      this._points = null;
    }
    this._paint(this._points, this._shownProgress || 0);
  }

  _seek(target) {
    const now = performance.now();
    if (this._shownProgress == null) {
      this._shownProgress = target;
      this._from = target;
      this._to = target;
      this._paint(this._points, target);
      this._setRing(target);
      return;
    }
    if (Math.abs(target - this._to) < 0.05 && this._raf) return;
    this._from = this._shownProgress;
    this._to = target;
    this._t0 = now;
    const elapsed = this._lastSeek ? now - this._lastSeek : 900;
    this._lastSeek = now;
    this._dur = Math.max(350, Math.min(2500, elapsed));
    if (!this._raf) this._raf = requestAnimationFrame(() => this._frame());
  }

  _frame() {
    const u = Math.min(1, (performance.now() - this._t0) / this._dur);
    const eased = u * u * (3 - 2 * u);
    this._shownProgress = this._from + (this._to - this._from) * eased;
    this._setRing(this._shownProgress);
    if (this._points) this._paint(this._points, this._shownProgress);
    if (u < 1) this._raf = requestAnimationFrame(() => this._frame());
    else this._raf = 0;
  }

  _setRing(percent) {
    const length = 2 * Math.PI * 46;
    const value = this._card.querySelector(".ring .value");
    value.style.strokeDasharray = `${length}`;
    value.style.strokeDashoffset = `${length * (1 - Math.max(0, Math.min(100, percent)) / 100)}`;
  }

  _paint(points, percent) {
    const ctx = this._ctx;
    const size = this._canvas.width;
    const center = size / 2;
    const radius = center - 8;
    ctx.clearRect(0, 0, size, size);
    const gradient = ctx.createRadialGradient(center, center, radius * 0.2, center, center, radius);
    gradient.addColorStop(0, "#f2dfc0");
    gradient.addColorStop(1, "#c49662");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.fill();
    if (!points || points.length < 2) return;
    const plot = points.map(([theta, rho]) => [
      center + Math.cos(theta) * rho * radius,
      center - Math.sin(theta) * rho * radius,
    ]);
    const index = Math.max(0, Math.min(plot.length - 1, (percent / 100) * (plot.length - 1)));
    const cut = Math.floor(index);
    const part = index - cut;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(120, 86, 52, 0.18)";
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    plot.forEach((point, i) => (i ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1])));
    ctx.stroke();
    const next = plot[Math.min(plot.length - 1, cut + 1)];
    const curr = plot[cut];
    const ball = [curr[0] + (next[0] - curr[0]) * part, curr[1] + (next[1] - curr[1]) * part];
    ctx.strokeStyle = "#3a2818";
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    for (let i = 0; i <= cut; i += 1) {
      const point = plot[i];
      if (i === 0) ctx.moveTo(point[0], point[1]);
      else ctx.lineTo(point[0], point[1]);
    }
    if (cut < plot.length - 1) ctx.lineTo(ball[0], ball[1]);
    ctx.stroke();
    ctx.fillStyle = "#fffaf2";
    ctx.strokeStyle = "#1c140e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(ball[0], ball[1], 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  _updateGallery() {
    const gallery = this._found.gallery;
    const order = this._attr(gallery, "category_order") || [];
    const categories = this._attr(gallery, "categories") || {};
    this._categories = categories;
    if (!this._category) this._category = order[0] || "My Patterns";
    if (this._category !== "My Patterns" && !this._picked) {
      this._picked = this._state(gallery) || (this._attr(gallery, "options") || [])[0] || "";
    }
    const favState = this._found.favorites && this._hass.states[this._found.favorites];
    this._favorites = (favState && favState.attributes && favState.attributes.options) || [];
    const tabs = this._card.querySelector(".tabs");
    const names = ["My Patterns", ...(order.length ? order : ["All"])];
    if (this._deviceId && this._mineDevice !== this._deviceId) {
      this._mineDevice = this._deviceId;
      this._loadMine();
    }
    if (tabs.dataset.key !== names.join("|") + this._category) {
      tabs.replaceChildren();
      names.forEach((cat) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.cat = cat;
        button.textContent = cat;
        button.classList.toggle("active", cat === this._category);
        tabs.appendChild(button);
      });
      tabs.dataset.key = names.join("|") + this._category;
    }
    this._renderGrid();
    this._card.querySelector(".pick .label").textContent = this._picked || "";
    const heart = this._card.querySelector(".heart");
    const mine = this._category === "My Patterns";
    heart.hidden = mine;
    const loved = !mine && this._picked && this._favorites.includes(this._picked);
    heart.textContent = loved ? "Favorited" : "Favorite";
    heart.classList.toggle("on", Boolean(loved));
    setDisabled(this._card.querySelector(".draw"), mine && this._state(this._found.power) !== "on");
  }

  async _loadMine() {
    if (!this._hass || !this._deviceId || !this._hass.callApi) return;
    const deviceId = this._deviceId;
    try {
      const data = await this._hass.callApi("GET", `homedics_drift/library/${encodeURIComponent(deviceId)}`);
      if (this._mineDevice !== deviceId) return;
      this._mine = (data && data.patterns) || [];
    } catch (_err) {
      this._mine = [];
    }
    if (this._category === "My Patterns") {
      const names = (this._mine || []).map((item) => item.name);
      if (!names.includes(this._picked)) this._picked = names[0] || "";
      if (this._card) this._card.querySelector(".grid").dataset.key = "";
      this._updateGallery();
    }
  }

  _renderGrid() {
    const grid = this._card.querySelector(".grid");
    if (this._category === "My Patterns") {
      const items = this._mine || [];
      const key = items.map((item) => item.pattern_id).join("|") + "|" + this._picked;
      if (grid.dataset.key === key) return;
      grid.dataset.key = key;
      grid.replaceChildren();
      items.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.name = item.name;
        button.classList.toggle("picked", item.name === this._picked);
        const img = document.createElement("img");
        img.alt = item.name;
        if (item.preview) img.src = item.preview;
        button.appendChild(img);
        grid.appendChild(button);
      });
      if (!items.length) {
        const empty = document.createElement("p");
        empty.className = "import-status";
        empty.textContent = "No saved patterns yet.";
        grid.appendChild(empty);
      }
      return;
    }
    const names = Object.keys(this._categories || {}).filter((name) => !this._category || this._category === "All" || this._categories[name] === this._category);
    const byName = {};
    (this._tiles || []).forEach((id) => {
      const state = this._hass.states[id];
      if (!state) return;
      const friendly = state.attributes.friendly_name || "";
      Object.keys(this._categories || {}).forEach((name) => {
        const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
        if (friendly.endsWith(name) || (slug && id.endsWith("_" + slug))) byName[name] = state;
      });
    });
    const key = names.join("|") + "|" + this._picked;
    if (grid.dataset.key === key) return;
    grid.dataset.key = key;
    grid.replaceChildren();
    names.forEach((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.name = name;
      button.classList.toggle("picked", name === this._picked);
      const img = document.createElement("img");
      img.alt = name;
      const state = byName[name];
      if (state && state.attributes.entity_picture) img.src = state.attributes.entity_picture;
      button.appendChild(img);
      grid.appendChild(button);
    });
  }

  _updateCreate() {
    const area = this._card.querySelector(".prompt");
    if (document.activeElement !== area) {
      const current = this._state(this._found.prompt);
      if (current && current !== "unknown" && !area.value) area.value = current;
    }
    const status = this._state(this._found.ai) || "";
    const detail = this._attr(this._found.ai, "detail") || this._attr(this._found.ai, "error") || "";
    const progress = Number(this._attr(this._found.ai, "progress"));
    this._card.querySelector(".status").textContent = [status, detail].filter((part) => part && part !== "unknown").join(" · ");
    const width = Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : status === "stored" ? 100 : 0;
    this._card.querySelector(".ai-bar").style.width = width + "%";
  }

  _updateFoot() {
    const used = Number(this._state(this._found.slots));
    const cap = Number(this._attr(this._found.slots, "cap")) || 700;
    const safeUsed = Number.isFinite(used) ? used : 0;
    this._card.querySelector(".slots").textContent = `${safeUsed} / ${cap}`;
    this._card.querySelector(".slot-bar").style.width = Math.max(0, Math.min(100, (safeUsed / cap) * 100)) + "%";
    const powerOn = this._state(this._found.power) === "on";
    this._card.querySelectorAll(".clean").forEach((el) => setDisabled(el, !powerOn || !this._found.clean));
  }
}

if (!customElements.get("drift-table-card")) {
  customElements.define("drift-table-card", DriftTableCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: "drift-table-card",
  name: "Drift Table",
  description: "Sand, transport, light, and speed, with table patterns and the gallery under More",
});

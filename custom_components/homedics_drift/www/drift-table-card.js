// Drift table card. Loaded by the integration; no separate frontend install.
// Theme colors come from Home Assistant CSS variables. Frosted glass is opt-in.

import { resolveDriftEntities } from "./drift-table-resolve.js";

const SHOW = ["show_now", "show_gallery", "show_create", "show_storage", "show_clean", "show_light", "show_speed"];

class DriftTableCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getConfigForm() {
    const flag = (name, label) => ({ name, selector: { boolean: {} }, helper: label });
    return {
      schema: [
        { name: "entity", selector: { entity: {} } },
        { name: "device", selector: { device: {} } },
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
        flag("show_gallery", "Gallery"),
        flag("show_create", "Create"),
        flag("show_light", "Light"),
        flag("show_speed", "Speed"),
        flag("show_clean", "Clean Sand"),
        flag("show_storage", "Storage"),
      ],
    };
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.device && !config.device_id)) {
      throw new Error("Choose a Drift entity or device");
    }
    this._config = config;
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._ensure();
    this._update();
  }

  getCardSize() {
    return 8;
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

  _ensure() {
    const style = this._styleName();
    if (this._built && this._styleApplied === style) return;
    this._styleApplied = style;
    this._built = true;
    this._points = null;
    this._pathFor = null;
    this._shownProgress = null;
    const card = document.createElement("ha-card");
    card.className = "drift-table" + (style === "native" ? "" : " " + style);
    card.innerHTML = `
      <style>
        :host { display: block; }
        ha-card.drift-table { color: var(--primary-text-color); border-radius: var(--ha-card-border-radius, 12px); overflow: hidden; }
        ha-card.drift-table.frosted { --ha-card-background: color-mix(in srgb, var(--card-background-color, var(--ha-card-background, #fff)) 62%, transparent); backdrop-filter: blur(18px); border: 1px solid var(--divider-color); }
        ha-card.drift-table.minimal { --ha-card-background: transparent; --ha-card-box-shadow: none; box-shadow: none; }
        .body { padding: 16px; display: flex; flex-direction: column; gap: 18px; }
        h2 { margin: 0 0 8px; font-size: 1.05rem; font-weight: 500; color: var(--primary-text-color); }
        .missing { margin: 0; color: var(--primary-text-color); }
        .stage { position: relative; width: min(100%, 280px); margin: 0 auto; aspect-ratio: 1; }
        .ring { position: absolute; inset: 0; width: 100%; height: 100%; }
        .ring circle.track { fill: none; stroke: var(--divider-color); stroke-width: 6; }
        .ring circle.value { fill: none; stroke: var(--primary-color); stroke-width: 6; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 50% 50%; }
        .sand { position: absolute; inset: 11%; border-radius: 50%; overflow: hidden; background: #e4c79a; box-shadow: 0 0 0 2px var(--glow, var(--divider-color)), 0 0 22px 2px var(--glow, transparent); }
        canvas, .still { width: 100%; height: 100%; display: block; object-fit: cover; }
        .still[hidden], canvas[hidden] { display: none; }
        .name { text-align: center; margin: 8px 0 0; font-size: 1.05rem; }
        .row { display: flex; justify-content: center; align-items: center; gap: 2px; flex-wrap: wrap; }
        button { background: transparent; color: var(--primary-text-color); border: none; border-radius: var(--ha-card-border-radius, 8px); padding: 8px 10px; font: inherit; cursor: pointer; }
        button:hover { background: var(--secondary-background-color); }
        button:disabled { color: var(--disabled-text-color); cursor: default; background: transparent; }
        button.accent { color: var(--primary-color); font-weight: 600; }
        button.on { color: var(--primary-color); }
        .field { display: flex; align-items: center; gap: 8px; margin-top: 8px; color: var(--primary-text-color); }
        .field span { width: 4.5rem; flex: none; }
        input[type="range"] { flex: 1; accent-color: var(--primary-color); }
        input[type="color"] { width: 36px; height: 28px; border: none; background: transparent; padding: 0; }
        .tabs { display: flex; gap: 4px; overflow-x: auto; margin-bottom: 8px; }
        .tabs button { white-space: nowrap; color: var(--secondary-text-color); }
        .tabs button.active { color: var(--primary-color); box-shadow: inset 0 -2px 0 var(--primary-color); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 8px; max-height: 320px; overflow: auto; }
        .grid button { padding: 0; border-radius: var(--ha-card-border-radius, 8px); overflow: hidden; }
        .grid button.picked { outline: 2px solid var(--primary-color); }
        .grid img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
        .pick { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
        .pick .label { flex: 1; }
        textarea, .import-url { width: 100%; box-sizing: border-box; font: inherit; color: var(--primary-text-color); background: var(--secondary-background-color, transparent); border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 8px); padding: 8px; }
        textarea { min-height: 72px; resize: vertical; }
        .import-status { margin-top: 6px; color: var(--secondary-text-color); min-height: 1.2em; }
        .bar { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; margin-top: 8px; }
        .bar span { display: block; height: 100%; width: 0; background: var(--primary-color); }
        .status { margin-top: 6px; color: var(--secondary-text-color); min-height: 1.2em; }
        .meter { display: flex; align-items: center; gap: 8px; }
        .meter .bar { flex: 1; margin: 0; }
        .foot { display: flex; flex-direction: column; gap: 10px; }
        @media (max-width: 520px) { .body { padding: 12px; } }
      </style>
      <div class="body">
        <p class="missing" hidden>This card could not find the Drift player. Set the card to that media player, or to the Drift device.</p>
        <section class="now"><h2>Now Playing</h2>
          <div class="stage">
            <svg class="ring" viewBox="0 0 100 100" aria-hidden="true"><circle class="track" cx="50" cy="50" r="46"></circle><circle class="value" cx="50" cy="50" r="46"></circle></svg>
            <div class="sand"><canvas width="320" height="320"></canvas><img class="still" alt="" hidden></div>
          </div>
          <div class="name"></div>
          <div class="row transport"></div>
          <div class="light field"><span>Light</span><input type="color" aria-label="Light Color"><input type="range" min="0" max="255" aria-label="Brightness"></div>
          <div class="speed field"><span>Speed</span><input type="range" min="0" max="100" aria-label="Speed"></div>
        </section>
        <section class="gallery"><h2>Gallery</h2><div class="tabs"></div><div class="grid"></div>
          <div class="pick"><span class="label"></span><button type="button" class="heart">Favorite</button><button type="button" class="accent draw">Draw</button></div>
        </section>
        <section class="create"><h2>Create</h2><textarea aria-label="AI Prompt" placeholder="A twelve pointed star"></textarea>
          <div class="row"><button type="button" class="accent ai">Draw With AI</button></div>
          <div class="bar"><span class="ai-bar"></span></div><div class="status"></div>
          <h2>Import</h2>
          <input class="import-url" type="url" aria-label="Pattern Link" placeholder="https://… .thr or .gcode">
          <div class="row"><button type="button" class="accent import">Import</button></div>
          <div class="import-status"></div>
        </section>
        <div class="foot">
          <button type="button" class="clean">Clean Sand</button>
          <div class="meter"><span class="slots"></span><div class="bar"><span class="slot-bar"></span></div></div>
        </div>
      </div>`;
    this.shadowRoot.replaceChildren(card);
    this._card = card;
    this._canvas = card.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
    this._bind(card);
  }

  _bind(card) {
    const call = (domain, service, data) => {
      if (!this._hass) return;
      if (data && Object.prototype.hasOwnProperty.call(data, "entity_id") && !data.entity_id) return;
      this._hass.callService(domain, service, data);
    };
    card.querySelector(".transport").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      const id = this._found.player;
      const map = { prev: "media_previous_track", play: "media_play", pause: "media_pause", next: "media_next_track" };
      if (button.dataset.act === "power") {
        const on = this._state(this._found.power) === "on";
        call("switch", on ? "turn_off" : "turn_on", { entity_id: this._found.power });
        return;
      }
      if (button.dataset.role === "stop-after") {
        const on = this._state(this._found.stopAfter) === "on";
        call("switch", on ? "turn_off" : "turn_on", { entity_id: this._found.stopAfter });
        return;
      }
      const service = map[button.dataset.act];
      if (service && id) call("media_player", service, { entity_id: id });
    });
    const color = card.querySelector('input[type="color"]');
    const bright = card.querySelector(".light input[type=range]");
    const sendLight = () => {
      if (!this._found.light) return;
      const hex = color.value || "#ffffff";
      const value = parseInt(hex.slice(1), 16);
      call("light", "turn_on", {
        entity_id: this._found.light,
        rgb_color: [(value >> 16) & 255, (value >> 8) & 255, value & 255],
        brightness: Number(bright.value),
      });
    };
    color.addEventListener("change", sendLight);
    bright.addEventListener("change", sendLight);
    card.querySelector(".speed input").addEventListener("change", (event) => {
      if (this._found.speed) call("number", "set_value", { entity_id: this._found.speed, value: Number(event.target.value) });
    });
    card.querySelector(".draw").addEventListener("click", () => {
      const name = this._picked;
      if (!name || !this._deviceId) return;
      if (this._state(this._found.power) !== "on") return;
      if (this._category === "My Patterns") {
        call("select", "select_option", { entity_id: this._found.stored, option: name });
        return;
      }
      if (this._found.gallery) call("select", "select_option", { entity_id: this._found.gallery, option: name });
      call("homedics_drift", "add_gallery_design", { device_id: this._deviceId, name, play: true });
    });
    card.querySelector(".heart").addEventListener("click", () => {
      const name = this._picked;
      if (!name || !this._deviceId) return;
      const on = (this._favorites || []).includes(name);
      call("homedics_drift", "set_favorite", { device_id: this._deviceId, name, favorite: !on });
    });
    card.querySelector(".import").addEventListener("click", () => {
      const url = card.querySelector(".import-url").value.trim();
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
          note.textContent = (err && err.message) || "That link could not be imported.";
        });
    });
    card.querySelector(".ai").addEventListener("click", () => {
      const text = card.querySelector("textarea").value.trim();
      if (!text || !this._deviceId) return;
      if (this._found.prompt) call("text", "set_value", { entity_id: this._found.prompt, value: text });
      const powerOn = this._state(this._found.power) === "on";
      call("homedics_drift", "ai_draw", { device_id: this._deviceId, prompt: text, play: powerOn });
    });
    card.querySelector(".clean").addEventListener("click", () => {
      if (this._found.clean) call("button", "press", { entity_id: this._found.clean });
    });
    card.querySelector(".tabs").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      this._category = button.dataset.cat;
      if (this._category === "My Patterns") {
        const names = (this._mine || []).map((item) => item.name);
        if (!names.includes(this._picked)) this._picked = names[0] || "";
      }
      this._card.querySelector(".tabs").dataset.key = "";
      this._card.querySelector(".grid").dataset.key = "";
      this._updateGallery();
    });
    card.querySelector(".grid").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !button.dataset.name) return;
      this._picked = button.dataset.name;
      if (this._category !== "My Patterns" && this._found.gallery) {
        call("select", "select_option", { entity_id: this._found.gallery, option: this._picked });
      }
      this._renderGrid();
      this._card.querySelector(".pick .label").textContent = this._picked;
    });
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
    if (missing) missing.hidden = Boolean(this._found.player);
    card.querySelector(".now").hidden = !this._shown("show_now");
    card.querySelector(".gallery").hidden = !this._shown("show_gallery");
    card.querySelector(".create").hidden = !this._shown("show_create");
    card.querySelector(".light").hidden = !this._shown("show_light");
    card.querySelector(".speed").hidden = !this._shown("show_speed");
    card.querySelector(".clean").hidden = !this._shown("show_clean");
    card.querySelector(".meter").hidden = !this._shown("show_storage");
    this._updateNow();
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
    const transport = this._card.querySelector(".transport");
    if (!transport.childElementCount) {
      [["prev", "Prev"], ["play", "Play"], ["next", "Next"], ["power", "Power"], ["stop-after", "Stop After"]].forEach(([act, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.role = act;
        button.dataset.act = act;
        button.textContent = label;
        transport.appendChild(button);
      });
    }
    transport.querySelectorAll("button").forEach((button) => {
      if (button.dataset.role === "power") {
        button.textContent = powerOn ? "Power On" : "Power Off";
        button.classList.toggle("on", powerOn);
        button.disabled = false;
        return;
      }
      if (button.dataset.role === "stop-after") {
        const held = this._state(this._found.stopAfter) === "on";
        button.textContent = held ? "Stop After On" : "Stop After";
        button.classList.toggle("on", held);
        button.disabled = !this._found.stopAfter;
        return;
      }
      if (button.dataset.role === "play") {
        button.dataset.act = playing ? "pause" : "play";
        button.textContent = playing ? "Pause" : "Play";
      }
      button.disabled = !powerOn;
    });
    const color = this._card.querySelector('input[type="color"]');
    if (Array.isArray(rgb) && document.activeElement !== color) {
      color.value = "#" + rgb.map((part) => Number(part).toString(16).padStart(2, "0")).join("");
    }
    const bright = this._card.querySelector(".light input[type=range]");
    if (document.activeElement !== bright && this._attr(this._found.light, "brightness") != null) {
      bright.value = this._attr(this._found.light, "brightness");
    }
    const speed = this._card.querySelector(".speed input");
    if (document.activeElement !== speed && this._state(this._found.speed) != null) {
      speed.value = this._state(this._found.speed);
    }
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
    this._card.querySelector(".draw").disabled = mine && this._state(this._found.power) !== "on";
  }

  async _loadMine() {
    if (!this._hass || !this._deviceId || !this._hass.callApi) return;
    const deviceId = this._deviceId;
    try {
      const data = await this._hass.callApi(
        "GET",
        `homedics_drift/library/${encodeURIComponent(deviceId)}`,
      );
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
      const friendly = state && (state.attributes.friendly_name || "");
      const design = friendly.split(" ").slice(-2).join(" ");
      byName[state && state.attributes.friendly_name] = state;
      if (design) byName[design] = state;
    });
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
    const area = this._card.querySelector("textarea");
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
    const clean = this._card.querySelector(".clean");
    clean.disabled = this._state(this._found.power) !== "on";
  }
}

if (!customElements.get("drift-table-card")) {
  customElements.define("drift-table-card", DriftTableCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: "drift-table-card",
  name: "Drift Table",
  description: "Now playing, gallery, and AI drawing for a HoMedics Drift table",
});

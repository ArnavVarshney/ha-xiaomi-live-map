/* Xiaomi Live Map card: the robot's map, live position and cleaning path, streamed by the xiaomi_live_map integration.
 * https://github.com/ArnavVarshney/ha-xiaomi-live-map */
const NS = "http://www.w3.org/2000/svg";
const ROOM_COLORS = { 0: [176, 190, 210], 1: [142, 197, 252], 2: [250, 214, 128], 3: [129, 219, 196], 4: [247, 172, 188],
  5: [196, 181, 253], 6: [253, 186, 140] };
const WALL = [74, 88, 110], CLUTTER = [140, 150, 165];
const CELL = 4; // canvas pixels per map cell

const STYLE = `
:host{display:block}
ha-card{overflow:hidden;position:relative;height:100%}
.wrap{position:relative;width:100%;max-height:var(--xiaomi-live-map-max-height,720px);user-select:none;-webkit-user-select:none}
svg{display:block;width:100%;height:100%;touch-action:pan-y;cursor:pointer}
svg.zoomed{touch-action:none;cursor:grab}
.grid{image-rendering:pixelated;image-rendering:crisp-edges}
.carpet{fill:url(#hatch);stroke:rgba(255,255,255,.75);stroke-width:1.2;vector-effect:non-scaling-stroke;stroke-dasharray:4 3}
.vwall{stroke:#ef4444;stroke-width:3;vector-effect:non-scaling-stroke;stroke-linecap:round}
.nogo{fill:rgba(239,68,68,.25);stroke:#ef4444;stroke-width:1.5;vector-effect:non-scaling-stroke}
.nomop{fill:rgba(168,85,247,.22);stroke:#a855f7;stroke-width:1.5;vector-effect:non-scaling-stroke}
.zone{fill:rgba(255,255,255,.18);stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke;stroke-dasharray:6 4}
.mop{fill:none;stroke:rgba(255,255,255,.34);stroke-linecap:round;stroke-linejoin:round}
.path{fill:none;stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke;stroke-linecap:round;stroke-linejoin:round}
.last .path{stroke-opacity:.6}.last .mop{stroke-opacity:.6}
.labels{position:absolute;inset:0;pointer-events:none;overflow:hidden}
.label{position:absolute;transform:translate(-50%,-50%);white-space:nowrap;font-size:12px;font-weight:500;line-height:1;
  padding:5px 9px;border-radius:999px;background:rgba(255,255,255,.88);color:#1f2937;box-shadow:0 1px 3px rgba(0,0,0,.25);
  display:flex;align-items:center;gap:4px;transition:background .2s,color .2s}
.label.sel{background:var(--primary-color,#03a9f4);color:#fff}
.label .tick{display:none;font-weight:700}.label.sel .tick{display:inline}
.chips{position:absolute;left:10px;top:10px;right:10px;display:flex;flex-wrap:wrap;gap:6px;pointer-events:none}
.chip{font-size:12px;line-height:1;padding:6px 10px;border-radius:999px;background:rgba(17,24,39,.72);color:#fff;
  backdrop-filter:blur(4px);display:flex;align-items:center;gap:6px}
.chip.live::before{content:"";width:7px;height:7px;border-radius:50%;background:#22c55e;animation:pulse 1.6s infinite}
.chip.warn{background:rgba(180,83,9,.9)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.legend{position:absolute;left:10px;bottom:10px;display:flex;gap:10px;font-size:11px;padding:5px 10px;border-radius:999px;
  background:rgba(17,24,39,.72);color:#fff;pointer-events:none;align-items:center}
.legend i{display:inline-block;vertical-align:middle;margin-right:5px;border-radius:3px;background:#fff}
.legend .l1{width:16px;height:2px}.legend .l2{width:16px;height:8px;opacity:.45}
.legend[hidden],.wrap[hidden],.empty[hidden]{display:none}
.zoom{position:absolute;right:10px;bottom:10px;display:flex;flex-direction:column;gap:6px}
.zoom button{width:34px;height:34px;border-radius:50%;border:none;background:rgba(17,24,39,.72);color:#fff;font-size:18px;
  line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}
.zoom button[hidden]{display:none}
.empty{padding:32px 16px;text-align:center;color:var(--secondary-text-color)}
.toast{position:absolute;left:50%;bottom:54px;transform:translateX(-50%);font-size:12px;padding:7px 12px;border-radius:999px;
  background:rgba(17,24,39,.85);color:#fff;opacity:0;transition:opacity .25s;pointer-events:none;white-space:nowrap}
.toast.on{opacity:1}
.go{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);border:none;border-radius:999px;padding:10px 18px;font-size:13px;
  font-weight:600;background:var(--primary-color,#03a9f4);color:#fff;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.35);white-space:nowrap;max-width:62%;overflow:hidden;text-overflow:ellipsis}
.go[hidden]{display:none}.go.arm{background:#16a34a}
`;

function el(name, attrs, parent) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

class XiaomiLiveMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._n = 0; this._px = []; this._py = []; this._pm = [];
    this._idx = 0; this._done = 0; this._dPath = ""; this._dMop = ""; this._pen = false; this._penMop = false;
    this._pointers = new Map();
    this._selKey = "";
    this._localSel = new Set();
  }

  setConfig(config) {
    this._cfg = Object.assign({ rooms: {}, chips: [], mop_modes: [2, 3], mop_width: 300, max_height: 720 }, config || {});
    this._mopModes = new Set(this._cfg.mop_modes);
    this._build();
  }

  static getStubConfig() { return {}; }

  static getConfigForm() {
    return {
      schema: [
        { name: "status_entity", selector: { entity: {} } },
        { name: "chips", selector: { entity: { multiple: true } } },
        { name: "start_script", selector: { entity: { domain: "script" } } },
        { type: "grid", name: "", schema: [
          { name: "mop_width", selector: { number: { min: 50, max: 600, step: 10, unit_of_measurement: "mm", mode: "box" } } },
          { name: "max_height", selector: { number: { min: 200, max: 2000, step: 10, unit_of_measurement: "px", mode: "box" } } },
        ] },
        { name: "entry_id", selector: { config_entry: { integration: "xiaomi_live_map" } } },
      ],
      computeLabel: (s) => ({ status_entity: "Status entity (top-left chip)", chips: "Chips shown while cleaning",
        start_script: "Script that starts a room clean", mop_width: "Mop band width", max_height: "Maximum height",
        entry_id: "Robot (only needed with several robots)" })[s.name],
      computeHelper: (s) => ({ start_script: "Called with the variables rooms (ids) and room_names when you tap Clean.",
        chips: "For example area, time and battery sensors." })[s.name],
    };
  }
  getCardSize() { return 9; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  set hass(hass) {
    this._hass = hass;
    this._subscribe();
    this._updateChips();
    const key = this._selected().join(",");
    if (key !== this._selKey) { this._selKey = key; this._drawGrid(); this._updateLabels(); }
  }

  connectedCallback() { this._subscribe(); if (!this._ro && this._wrap) { this._ro = new ResizeObserver(() => this._layout()); this._ro.observe(this._wrap); } }
  disconnectedCallback() {
    if (this._unsub) { this._unsub.then((u) => u && u()).catch(() => {}); this._unsub = null; }
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    cancelAnimationFrame(this._raf); this._raf = 0;
  }

  _subscribe() {
    if (this._unsub || !this._hass || !this.isConnected) return;
    const msg = { type: "xiaomi_live_map/subscribe" };
    if (this._cfg.entry_id) msg.entry_id = this._cfg.entry_id;
    this._unsub = this._hass.connection.subscribeMessage((m) => this._onMsg(m), msg);
    this._unsub.catch((e) => {
      this._unsub = null; this._fatal = (e && e.message) || "Xiaomi Live Map is not set up";
      if (!this._base) this._empty.textContent = this._fatal;
      this._updateChips();
    });
  }

  _build() {
    const r = this.shadowRoot;
    r.innerHTML = `<style>${STYLE}</style><ha-card><div class="empty">Loading map…</div><div class="wrap" hidden>
      <svg><defs><pattern id="hatch" width="150" height="150" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="150" height="150" fill="rgba(255,255,255,.14)"/><line x1="0" y1="0" x2="0" y2="150" stroke="rgba(255,255,255,.45)" stroke-width="34"/></pattern>
      <filter id="sh" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="0.06" stdDeviation="0.09" flood-opacity=".45"/></filter></defs></svg>
      <div class="labels"></div><div class="chips"></div><div class="legend" hidden></div>
      <div class="zoom"><button class="rst" hidden title="Reset view">⟲</button><button class="in" title="Zoom in">+</button><button class="out" title="Zoom out">−</button></div>
      <button class="go" hidden></button><div class="toast"></div></div></ha-card>`;
    this._empty = r.querySelector(".empty"); this._wrap = r.querySelector(".wrap"); this._svg = r.querySelector("svg");
    this._labels = r.querySelector(".labels"); this._chips = r.querySelector(".chips"); this._legend = r.querySelector(".legend");
    this._toast = r.querySelector(".toast"); this._go = r.querySelector(".go"); this._go.addEventListener("click", () => this._start()); this._rst = r.querySelector(".rst");
    this._wrap.style.setProperty("--xiaomi-live-map-max-height", this._cfg.max_height + "px");
    const s = this._svg;
    this._img = el("image", { class: "grid", preserveAspectRatio: "none" }, s);
    this._gDeco = el("g", {}, s);
    this._gPath = el("g", {}, s);
    this._mop = el("path", { class: "mop" }, this._gPath);
    this._path = el("path", { class: "path" }, this._gPath);
    this._lead = el("line", { class: "path" }, this._gPath);
    this._dock = el("g", { filter: "url(#sh)" }, s);
    this._dock.innerHTML = `<circle r="1" fill="#22c55e"/><circle r="1" fill="none" stroke="#fff" stroke-width=".16"/>
      <path d="M.12-.62-.42.1h.3l-.1.52.54-.72h-.3z" fill="#fff"/>`;
    this._bot = el("g", {}, s);
    this._bot.innerHTML = `<g class="rot"><circle r="1" fill="#fff" filter="url(#sh)"/><circle r=".93" fill="none" stroke="#cbd5e1" stroke-width=".1"/>
      <circle cx=".3" r=".36" fill="#e2e8f0" stroke="#94a3b8" stroke-width=".08"/><circle cx=".3" r=".12" fill="var(--primary-color,#03a9f4)"/>
      <path d="M.82-.22 1 0 .82.22" fill="none" stroke="#64748b" stroke-width=".1" stroke-linecap="round"/></g>`;
    this._botRot = this._bot.querySelector(".rot");
    s.addEventListener("pointerdown", (e) => this._down(e));
    s.addEventListener("pointermove", (e) => this._move(e));
    s.addEventListener("pointerup", (e) => this._up(e));
    s.addEventListener("pointercancel", (e) => this._pointers.delete(e.pointerId));
    s.addEventListener("wheel", (e) => { if (!e.ctrlKey && !e.metaKey && !this._zoomed()) return; e.preventDefault(); this._zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
    s.addEventListener("dblclick", () => this._setView(this._home));
    r.querySelector(".in").addEventListener("click", () => this._zoomAt(1.5));
    r.querySelector(".out").addEventListener("click", () => this._zoomAt(1 / 1.5));
    this._rst.addEventListener("click", () => this._setView(this._home));
    if (this.isConnected && !this._ro) { this._ro = new ResizeObserver(() => this._layout()); this._ro.observe(this._wrap); }
    if (this._base) { this._drawBase(); this._rebuildPath(true); }
  }

  /* ---------- data ---------- */
  _onMsg(m) {
    if (m.closed) { // the integration reloaded: subscribe again shortly
      this._unsub = null; clearTimeout(this._resubT); this._resubT = setTimeout(() => this._subscribe(), 3000); return;
    }
    this._fatal = null;
    this._active = !!m.active; this._error = m.error; this._updated = m.updated;
    if (m.grid) { const b = atob(m.grid); const g = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) g[i] = b.charCodeAt(i); this._grid = g; }
    if ("last_path" in m) { this._lastPath = m.last_path || []; this._lastTs = m.last_ts; }
    const baseChanged = !!m.base;
    if (m.base) this._base = m.base;
    if (!this._base || !this._grid) { this._empty.textContent = m.error ? "Map unavailable: " + m.error : "Waiting for the map…"; this._updateChips(); return; }
    if (baseChanged || m.grid) this._drawBase();
    if ("robot" in m) this._robot = m.robot;
    if ("path_from" in m) {
      if (m.path_from > this._n) { // missed an update: start over with a full snapshot
        const u = this._unsub; this._unsub = null; if (u) u.then((f) => f && f()).catch(() => {}); this._subscribe(); return;
      }
      const first = this._first === undefined; this._first = false;
      this._n = m.path_from; this._px.length = this._py.length = this._pm.length = this._n;
      const p = m.path_pts || [];
      for (let i = 0; i < p.length; i += 4) { this._px.push(p[i]); this._py.push(p[i + 1]); this._pm.push(this._mopModes.has(p[i + 3])); }
      this._n = this._px.length;
      const jump = first || !this._active || this._n - 1 - this._idx > 150;
      if (m.path_from < this._done || this._showingLast) this._rebuildPath(jump); else if (jump) this._rebuildPath(true);
    }
    this._showLastIfIdle();
    this._updateChips(); this._updateGo();
    this._tick();
  }

  _selected() {
    if (!this._usesHelpers()) return [...this._localSel];
    const out = [];
    const rooms = this._cfg.rooms || {};
    for (const id in rooms) { const st = this._hass && this._hass.states[rooms[id]]; if (st && st.state === "on") out.push(+id); }
    return out;
  }

  _usesHelpers() { return Object.keys(this._cfg.rooms || {}).length > 0; }

  /* ---------- drawing ---------- */
  _drawBase() {
    const b = this._base, g = this._grid;
    let x0 = b.w, x1 = -1, y0 = b.h, y1 = -1;
    for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) if (g[y * b.w + x]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) { x0 = 0; y0 = 0; x1 = b.w - 1; y1 = b.h - 1; }
    const pad = 250;
    const wx0 = b.ox + x0 * b.res - pad, wx1 = b.ox + (x1 + 1) * b.res + pad, wy0 = b.oy + y0 * b.res - pad, wy1 = b.oy + (y1 + 1) * b.res + pad + 450; // extra room at the top for the status chips
    const home = { x: wx0, y: -wy1, w: wx1 - wx0, h: wy1 - wy0 };
    const homeChanged = !this._home || ["x", "y", "w", "h"].some((k) => this._home[k] !== home[k]);
    this._home = home;
    this._wrap.style.aspectRatio = `${home.w} / ${home.h}`;
    this._empty.hidden = true; this._wrap.hidden = false;
    for (const [k, v] of Object.entries({ x: b.ox, y: -(b.oy + b.h * b.res), width: b.w * b.res, height: b.h * b.res })) this._img.setAttribute(k, v);
    this._mop.setAttribute("stroke-width", this._cfg.mop_width);
    this._drawGrid();
    // carpets, virtual walls, restricted areas, zones
    const d = this._gDeco; d.innerHTML = "";
    const poly = (p, cls) => { let s = ""; for (let i = 0; i + 1 < p.length; i += 2) s += `${p[i]},${-p[i + 1]} `; el("polygon", { points: s, class: cls }, d); };
    (b.carpets || []).forEach((p) => poly(p, "carpet"));
    (b.regions || []).forEach((r) => { if (r.type === "wall") el("line", { x1: r.p[0], y1: -r.p[1], x2: r.p[4], y2: -r.p[5], class: "vwall" }, d); else poly(r.p, r.type === "no_mop" ? "nomop" : "nogo"); });
    (b.vwalls || []).forEach((w) => el("line", { x1: w[0], y1: -w[1], x2: w[2], y2: -w[3], class: "vwall" }, d));
    (b.zones || []).forEach((z) => el("rect", { x: Math.min(z[0], z[2]), y: -Math.max(z[1], z[3]), width: Math.abs(z[2] - z[0]), height: Math.abs(z[3] - z[1]), class: "zone" }, d));
    // labels
    this._labels.innerHTML = "";
    this._labelEls = (b.rooms || []).filter((r) => r.name && r.x != null).map((r) => {
      const e = document.createElement("div"); e.className = "label"; e.innerHTML = `<span class="tick">✓</span><span></span>`;
      e.lastChild.textContent = r.name; this._labels.appendChild(e); return { r, e };
    });
    if (homeChanged || !this._view) this._setView(home); else this._layout();
  }

  _drawGrid() {
    const b = this._base, g = this._grid;
    if (!b || !g) return;
    const c = this._canvas || (this._canvas = document.createElement("canvas"));
    c.width = b.w * CELL; c.height = b.h * CELL;
    const ctx = c.getContext("2d"), img = ctx.createImageData(c.width, c.height), px = img.data;
    const colors = {}; (b.rooms || []).forEach((r) => { colors[r.id] = ROOM_COLORS[r.color] || ROOM_COLORS[(r.id % 6) + 1]; });
    const sel = new Set(this._selected()), dim = sel.size > 0;
    for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
      const v = g[y * b.w + x]; if (!v) continue;
      let col, a = 255;
      if (v === 1) col = WALL; else if (v === 2) { col = CLUTTER; a = 70; } else if (v <= 63) { col = colors[v] || ROOM_COLORS[0]; if (dim && !sel.has(v)) a = 105; } else col = WALL;
      const cy = (b.h - 1 - y) * CELL;
      for (let j = 0; j < CELL; j++) { let o = ((cy + j) * c.width + x * CELL) * 4; for (let i = 0; i < CELL; i++, o += 4) { px[o] = col[0]; px[o + 1] = col[1]; px[o + 2] = col[2]; px[o + 3] = a; } }
    }
    ctx.putImageData(img, 0, 0);
    this._img.setAttribute("href", c.toDataURL());
  }

  _append(to) { // extend the drawn path up to point index `to` (inclusive)
    for (let i = this._done; i <= to; i++) {
      const x = this._px[i], y = -this._py[i];
      const gap = i > 0 && Math.hypot(this._px[i] - this._px[i - 1], this._py[i] - this._py[i - 1]) > 1500;
      this._dPath += (i === 0 || gap ? "M" : "L") + x + " " + y;
      const mop = this._pm[i] && i > 0 && this._pm[i - 1] && !gap;
      if (mop) this._dMop += (this._penMop ? "L" : "M" + this._px[i - 1] + " " + -this._py[i - 1] + "L") + x + " " + y;
      this._penMop = mop;
    }
    this._done = Math.max(this._done, to + 1);
    this._path.setAttribute("d", this._dPath); this._mop.setAttribute("d", this._dMop);
  }

  _rebuildPath(jump) {
    this._dPath = ""; this._dMop = ""; this._done = 0; this._penMop = false; this._showingLast = false;
    this._gPath.classList.remove("last");
    if (jump) this._idx = Math.max(0, this._n - 1); else this._idx = Math.min(this._idx, Math.max(0, this._n - 1));
    if (this._n) this._append(Math.floor(this._idx)); else { this._path.setAttribute("d", ""); this._mop.setAttribute("d", ""); }
  }

  _showLastIfIdle() {
    const want = !this._active && this._n <= 2 && this._lastPath && this._lastPath.length >= 8;
    if (want && !this._showingLast) {
      const p = this._lastPath; let d = "", dm = "", pen = false;
      for (let i = 0; i < p.length; i += 4) {
        const gap = i > 0 && Math.hypot(p[i] - p[i - 4], p[i + 1] - p[i - 3]) > 1500;
        d += (i === 0 || gap ? "M" : "L") + p[i] + " " + -p[i + 1];
        const mop = i > 0 && !gap && this._mopModes.has(p[i + 3]) && this._mopModes.has(p[i - 1]);
        if (mop) dm += (pen ? "L" : "M" + p[i - 4] + " " + -p[i - 3] + "L") + p[i] + " " + -p[i + 1];
        pen = mop;
      }
      this._path.setAttribute("d", d); this._mop.setAttribute("d", dm); this._gPath.classList.add("last"); this._showingLast = true;
    } else if (!want && this._showingLast) this._rebuildPath(true);
    const any = this._showingLast || this._n > 2;
    this._legend.hidden = !any;
    if (any) this._legend.innerHTML = `<span><i class="l1"></i>Vacuumed</span><span><i class="l2"></i>Mopped</span>`;
  }

  _tick() {
    if (this._raf) return;
    let prev = performance.now();
    const step = (now) => {
      this._raf = 0;
      const dt = Math.min(0.1, (now - prev) / 1000); prev = now;
      const target = Math.max(0, this._n - 1);
      let moving = false;
      if (!this._showingLast && this._idx < target) {
        const speed = Math.max(1.5, (target - this._idx) / 2.5); // points per second: catch up in about 2.5 s
        this._idx = Math.min(target, this._idx + speed * dt);
        const whole = Math.floor(this._idx);
        if (whole >= this._done) this._append(whole);
        moving = true;
      }
      this._placeRobot(moving);
      if (moving && this.isConnected) this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }

  _placeRobot(moving) {
    const r = this._robot; let x, y, yaw = this._yaw || 0;
    const i = Math.floor(this._idx), n = this._n;
    if (moving && n > 1 && i + 1 < n) {
      const f = this._idx - i; x = this._px[i] + (this._px[i + 1] - this._px[i]) * f; y = this._py[i] + (this._py[i + 1] - this._py[i]) * f;
      const dx = this._px[i + 1] - this._px[i], dy = this._py[i + 1] - this._py[i];
      if (dx * dx + dy * dy > 100) yaw = Math.atan2(dy, dx);
      this._lead.setAttribute("x1", this._px[i]); this._lead.setAttribute("y1", -this._py[i]); this._lead.setAttribute("x2", x); this._lead.setAttribute("y2", -y);
      this._lead.style.display = "";
    } else {
      this._lead.style.display = "none";
      if (r) { x = r.x; y = r.y; yaw = r.yaw; } else if (n) { x = this._px[n - 1]; y = this._py[n - 1]; } else { this._bot.style.display = "none"; return; }
    }
    // turn the short way round
    let cur = this._yaw === undefined ? yaw : this._yaw, diff = yaw - cur;
    while (diff > Math.PI) diff -= 2 * Math.PI; while (diff < -Math.PI) diff += 2 * Math.PI;
    this._yaw = moving ? cur + diff * 0.25 : yaw;
    this._rx = x; this._ry = y; this._bot.style.display = "";
    this._bot.setAttribute("transform", `translate(${x} ${-y}) scale(${this._iconR || 170})`);
    this._botRot.setAttribute("transform", `rotate(${(-this._yaw * 180) / Math.PI})`);
  }

  /* ---------- view, labels, chips ---------- */
  _scale() { const r = this._wrap.getBoundingClientRect(), v = this._view; const s = Math.min(r.width / v.w, r.height / v.h); return { s, ox: (r.width - v.w * s) / 2, oy: (r.height - v.h * s) / 2, r }; }
  _zoomed() { return this._view && this._home && this._view.w < this._home.w * 0.98; }

  _setView(v) {
    if (!v) return;
    const h = this._home; let w = Math.min(h.w, Math.max(h.w / 8, v.w)); const hh = (w * h.h) / h.w;
    let x = Math.min(h.x + h.w - w, Math.max(h.x, v.x)), y = Math.min(h.y + h.h - hh, Math.max(h.y, v.y));
    this._view = { x, y, w, h: hh };
    this._svg.setAttribute("viewBox", `${x} ${y} ${w} ${hh}`);
    this._svg.classList.toggle("zoomed", this._zoomed()); this._rst.hidden = !this._zoomed();
    this._layout();
  }

  _zoomAt(f, cx, cy) {
    const v = this._view; if (!v) return;
    const { s, ox, oy, r } = this._scale();
    const px = cx === undefined ? r.width / 2 : cx - r.left, py = cy === undefined ? r.height / 2 : cy - r.top;
    const wx = v.x + (px - ox) / s, wy = v.y + (py - oy) / s, w = v.w / f, h = v.h / f;
    this._setView({ x: wx - ((wx - v.x) * w) / v.w, y: wy - ((wy - v.y) * h) / v.h, w, h });
  }

  _layout() {
    if (!this._view || !this._base) return;
    const { s, ox, oy, r } = this._scale(); if (!r.width) return;
    const v = this._view, sel = new Set(this._selected());
    (this._labelEls || []).forEach(({ r: room, e }) => {
      e.style.left = ox + (room.x - v.x) * s + "px"; e.style.top = oy + (-room.y - v.y) * s + "px";
      e.classList.toggle("sel", sel.has(room.id));
    });
    this._iconR = Math.max(170, 11 / s);
    const c = this._base.charger;
    if (c) { this._dock.style.display = ""; this._dock.setAttribute("transform", `translate(${c.x} ${-c.y}) scale(${Math.max(150, 10 / s)})`); } else this._dock.style.display = "none";
    this._placeRobot(false);
  }
  _updateLabels() { this._layout(); this._updateGo(); }
  _selChanged() { this._selKey = this._selected().join(","); this._drawGrid(); this._updateLabels(); }

  _updateGo() { // "Clean <rooms>" button, shown while rooms are picked and the robot is free
    if (!this._go) return;
    const sel = this._selected(), names = ((this._base && this._base.rooms) || []).filter((r) => sel.includes(r.id)).map((r) => r.name);
    const show = !!this._cfg.start_script && sel.length > 0 && !this._active;
    this._go.hidden = !show; this._legend.style.visibility = show ? "hidden" : "";
    if (!show) { this._armed = false; return; }
    this._go.classList.toggle("arm", !!this._armed);
    this._go.textContent = this._armed ? "Tap again to start" : "▶ Clean " + (names.length > 2 ? names.length + " rooms" : names.join(" + "));
  }

  _start() {
    if (!this._armed) { this._armed = true; this._updateGo(); clearTimeout(this._armT); this._armT = setTimeout(() => { this._armed = false; this._updateGo(); }, 4000); return; }
    this._armed = false; clearTimeout(this._armT);
    const ids = this._selected(), names = ((this._base && this._base.rooms) || []).filter((r) => ids.includes(r.id)).map((r) => r.name);
    this._hass.callService("script", "turn_on", { entity_id: this._cfg.start_script, variables: { rooms: ids, room_names: names } });
    if (!this._usesHelpers()) { this._localSel.clear(); this._selChanged(); }
    this._say("Starting — the robot first finds its position"); this._updateGo();
  }

  _updateChips() {
    if (!this._chips) return;
    const h = this._hass, out = [];
    const add = (text, cls) => { const e = document.createElement("div"); e.className = "chip " + (cls || ""); e.textContent = text; out.push(e); };
    if (this._fatal) add("Map data unavailable: " + this._fatal, "warn");
    if (h) {
      const st = this._cfg.status_entity && h.states[this._cfg.status_entity];
      if (st) add(st.state, this._active ? "live" : "");
      else if (this._active) add("Cleaning", "live");
      (this._active ? this._cfg.chips : []).forEach((id) => { const s = h.states[id]; if (s && !["unknown", "unavailable"].includes(s.state)) add(s.state + (s.attributes.unit_of_measurement ? " " + s.attributes.unit_of_measurement : "")); });
    }
    if (this._showingLast) add("Last clean" + (this._lastTs ? " · " + new Date(this._lastTs * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""));
    if (this._error && this._base) add("Not updating: " + this._error, "warn");
    this._chips.replaceChildren(...out);
  }

  _say(text) { this._toast.textContent = text; this._toast.classList.add("on"); clearTimeout(this._toastT); this._toastT = setTimeout(() => this._toast.classList.remove("on"), 2200); }

  /* ---------- pointer handling ---------- */
  _down(e) {
    this._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, t: performance.now(), moved: false });
    if (this._zoomed() || this._pointers.size > 1) { try { this._svg.setPointerCapture(e.pointerId); } catch (_) {} }
    if (this._pointers.size === 2) { const [a, b] = [...this._pointers.values()]; this._pinch = Math.hypot(a.x - b.x, a.y - b.y); }
  }
  _move(e) {
    const p = this._pointers.get(e.pointerId); if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
    if (Math.hypot(e.clientX - p.sx, e.clientY - p.sy) > 8) p.moved = true;
    if (this._pointers.size === 2) {
      const [a, b] = [...this._pointers.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (this._pinch > 0 && d > 0) this._zoomAt(d / this._pinch, (a.x + b.x) / 2, (a.y + b.y) / 2);
      this._pinch = d; a.moved = b.moved = true;
    } else if (this._zoomed() && p.moved) {
      const { s } = this._scale(), v = this._view; this._setView({ x: v.x - dx / s, y: v.y - dy / s, w: v.w, h: v.h });
    }
  }
  _up(e) {
    const p = this._pointers.get(e.pointerId); this._pointers.delete(e.pointerId);
    if (!p || p.moved || this._pointers.size || performance.now() - p.t > 600) return;
    const b = this._base; if (!b) return;
    const { s, ox, oy, r } = this._scale(), v = this._view;
    const wx = v.x + (e.clientX - r.left - ox) / s, wy = -(v.y + (e.clientY - r.top - oy) / s);
    const cx = Math.floor((wx - b.ox) / b.res), cy = Math.floor((wy - b.oy) / b.res);
    if (cx < 0 || cy < 0 || cx >= b.w || cy >= b.h) return;
    const id = this._grid[cy * b.w + cx];
    if (!(b.rooms || []).some((r) => r.id === id) || !this._hass) return;
    if (this._active) { this._say("The robot is busy — rooms can be picked once it is done"); return; }
    if (this._usesHelpers()) {
      const ent = this._cfg.rooms[id];
      if (ent) this._hass.callService("homeassistant", "toggle", { entity_id: ent });
      return;
    }
    if (this._localSel.has(id)) this._localSel.delete(id); else this._localSel.add(id);
    this._selChanged();
  }
}

if (!customElements.get("xiaomi-live-map-card")) {
  customElements.define("xiaomi-live-map-card", XiaomiLiveMapCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "xiaomi-live-map-card", name: "Xiaomi Live Map", preview: false,
    description: "Live robot vacuum map with position, vacuum and mop paths", documentationURL: "https://github.com/ArnavVarshney/ha-xiaomi-live-map" });
}

/**
 * Lovelace card: BPS floor map with one or more trackers.
 *
 * Resource (Settings -> Dashboards -> ... -> Resources):
 *   URL: /bps/bps-map-card.js
 *   Type: JavaScript module
 *
 * YAML example:
 *   type: custom:bps-map-card
 *   floor: Livingroom
 *   entities:
 *     - sensor.phone_alice
 *     - sensor.phone_bob
 *   show_labels: false
 *   scale_labels: 100
 *   scale_icon: 100
 *   zone_label: false
 *   show_zone_labels: false    (draw zone and sub-zone names at their centers)
 *   poll_interval: 3
 *   map_file: livingroom.jpg
 *   show_receivers: true
 *   show_receiver_labels: false
 *   scale_receiver_icon: 100   (defaults to scale_icon)
 *   scale_receiver_labels: 100 (defaults to scale_labels)
 *   receiver_timeout: 30       (seconds without adverts before a receiver is offline; min 10)
 *   receiver_status:
 *     nsp_kitchen: binary_sensor.nsp_kitchen_status
 *
 * Receivers placed on this floor in the BPS panel are drawn with the beacon
 * icon: black when the receiver is working, red when it is offline/unavailable.
 * Status is resolved per receiver, first match wins:
 *   1. The entity mapped in receiver_status, when given. Mapping a receiver
 *      to false (or "heuristic") skips steps 2-4 and forces the heuristic.
 *   2. Bermuda scanner liveness: the card calls the bermuda.dump_devices
 *      service and matches scanners by name slug. The receiver is working
 *      while the scanner heard any BLE advertisement within receiver_timeout
 *      seconds — the same signal as Bermuda's own scanner-status table, and
 *      the only tier that catches a proxy whose BLE scanning has wedged.
 *   3. binary_sensor.<receiver>_status, when it exists with device_class
 *      connectivity (the conventional ESPHome status sensor). Checked before
 *      tier 4 because ESPHome keeps this sensor available with state "off"
 *      when the device disconnects.
 *   4. Device availability: the HA device whose name slugifies to the
 *      receiver id (hass.devices) is online while any of its entities is not
 *      unavailable — works with any entity, e.g. an uptime sensor. A
 *      connectivity-class entity of the device is authoritative instead.
 *   5. Otherwise a receiver counts as working when at least one Bermuda
 *      sensor.*_distance_to_<receiver> entity reports a distance (Bermuda
 *      holds the last reading for its ~30 s distance timeout before the
 *      sensor goes to unknown, so a dead proxy turns red after about half a
 *      minute — and a live proxy with no tracker in range shows red).
 */
class BpsMapCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._shadow = this.attachShadow({ mode: "open" });
    this._wrap = document.createElement("div");
    this._wrap.className = "wrap";
    this._canvas = document.createElement("canvas");
    this._status = document.createElement("div");
    this._status.className = "status";
    this._wrap.appendChild(this._canvas);
    this._wrap.appendChild(this._status);
    this._shadow.appendChild(this._wrap);

    const style = document.createElement("style");
    style.textContent = `
      .wrap { position: relative; width: 100%; }
      canvas {
        display: block;
        width: 100%;
        max-width: 100%;
        height: auto;
        background: #f4f4f4;
      }
      .status { font: 12px/1.4 sans-serif; color: var(--secondary-text-color, #888); margin-top: 6px; }
    `;
    this._shadow.appendChild(style);

    this._baseImage = null;
    this._mapUrlLoaded = "";
    this._imgNaturalW = 0;
    this._imgNaturalH = 0;
    this._positions = new Map();
    this._entityByTrackerKey = new Map();
    this._trackerIcons = {};
    this._iconCache = new Map();
    this._tintedIconCache = new Map();
    this._receivers = [];
    this._subzones = [];
    this._zones = [];
    this._receiverStatuses = new Map();
    this._bermudaScanners = null;
    this._bermudaDumpAt = 0;
    this._nextBermudaDumpAt = 0;
    this._bermudaNewest = 0;
    this._devicesRef = null;
    this._deviceSlugMap = new Map();
    this._entitiesRef = null;
    this._deviceEntitiesMap = new Map();

    this._pollTimer = null;

    this._bootstrapPromise = null;
    this._runGeneration = 0;
    this._coordinateWidth = 2000; // Must match sidebar panel coordinate space.
    this._lastZoneLabelSignature = "";
    this._lastFloorPresenceSignature = "";
  }

  setConfig(config) {
    if (!config || !config.floor) {
      throw new Error("BPS card: set floor (must match floor name in BPS coordinates).");
    }
    if (!config.entities || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("BPS card: set at least one entity (for example sensor.phone).");
    }
    this._config = {
      floor: config.floor,
      entities: config.entities,
      show_labels: Boolean(config.show_labels),
      scale_labels: BpsMapCard.normalizePercent(config.scale_labels),
      scale_icon: BpsMapCard.normalizePercent(config.scale_icon),
      zone_label: Boolean(config.zone_label),
      poll_interval: Number(config.poll_interval) > 0 ? Number(config.poll_interval) : 3,
      image: config.image || "",
      map_file: config.map_file || "",
      show_receivers: Boolean(config.show_receivers),
      show_receiver_labels: Boolean(config.show_receiver_labels),
      show_sub_zones: Boolean(config.show_sub_zones),
      show_zone_labels: Boolean(config.show_zone_labels),
      scale_receiver_icon: BpsMapCard.inheritPercent(config.scale_receiver_icon, config.scale_icon),
      scale_receiver_labels: BpsMapCard.inheritPercent(config.scale_receiver_labels, config.scale_labels),
      receiver_timeout:
        Number(config.receiver_timeout) > 0 ? Math.max(10, Number(config.receiver_timeout)) : 30,
      receiver_status:
        config.receiver_status && typeof config.receiver_status === "object"
          ? config.receiver_status
          : {},
    };
    this._entityByTrackerKey = new Map(
      this._config.entities.map((eid) => [this._trackerKeyFromEntity(eid), eid]),
    );
    this._runGeneration += 1;
    const gen = this._runGeneration;
    this._stopPolling();
    this._bootstrapPromise = null;
    this._positions.clear();
    this._receivers = [];
    this._subzones = [];
    this._zones = [];
    this._receiverStatuses = new Map();
    // A reconfigure gets an immediate dump attempt; the previous scanner map
    // is kept to bridge the gap until it lands.
    this._nextBermudaDumpAt = 0;
    this._lastZoneLabelSignature = "";
    this._lastFloorPresenceSignature = "";
    this._baseImage = null;
    this._mapUrlLoaded = "";
    if (this._hass) {
      this._bootstrapPromise = this._bootstrap(gen);
    }
    this._setStatus("Configuration loaded.");
  }

  getCardSize() {
    return 1;
  }

  static getConfigElement() {
    return document.createElement("bps-map-card-editor");
  }

  static getStubConfig() {
    return {
      floor: "MyFloor",
      entities: ["sensor.phone_alice"],
      show_labels: false,
      scale_labels: 100,
      scale_icon: 100,
      zone_label: false,
      poll_interval: 3,
      show_receivers: false,
      show_receiver_labels: false,
      show_sub_zones: false,
      show_zone_labels: false,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config || !hass) return;

    if (!this._bootstrapPromise) {
      this._runGeneration += 1;
      const gen = this._runGeneration;
      this._bootstrapPromise = this._config ? this._bootstrap(gen) : null;
    }

    if (!this._bootstrapPromise) {
      return;
    }
    const genAtSchedule = this._runGeneration;
    this._bootstrapPromise.then(() => {
      if (genAtSchedule !== this._runGeneration) {
        return;
      }
      if (this._pollTimer) {
        // Polling already runs for this generation; restarting it on every
        // hass assignment would make state-change frequency, not
        // poll_interval, drive the poll cadence.
        return;
      }
      this._startPolling();
    });

    if (
      this._config.zone_label &&
      this._config.show_labels &&
      this._baseImage &&
      this._positions.size > 0
    ) {
      const sig = this._zoneLabelSignature();
      if (sig !== this._lastZoneLabelSignature) {
        this._lastZoneLabelSignature = sig;
        this._redraw();
      }
    }

    if (this._baseImage && this._config?.entities?.length) {
      const fs = this._floorPresenceSignature();
      if (fs !== this._lastFloorPresenceSignature) {
        this._lastFloorPresenceSignature = fs;
        this._prunePositionsByFloor();
        this._redraw();
        this._updateFloorStatus();
      }
    }
  }

  disconnectedCallback() {
    this._stopPolling();
  }

  _setStatus(text) {
    this._status.textContent = text;
  }

  _friendlyLabel(trackerKey) {
    const ent = this._entityByTrackerKey.get(trackerKey);
    if (!ent || !this._hass?.states?.[ent]) return trackerKey;
    return this._hass.states[ent].attributes?.friendly_name || ent;
  }

  static inheritPercent(value, fallback) {
    return BpsMapCard.normalizePercent(value, BpsMapCard.normalizePercent(fallback));
  }

  static normalizePercent(value, fallback = 100) {
    if (value == null || value === "") return fallback;
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return value;
    }
    const s = String(value).trim();
    const m = s.match(/^(\d+(?:\.\d+)?)\s*%?\s*$/);
    if (m) {
      const n = Number(m[1]);
      return Number.isFinite(n) && n > 0 ? n : fallback;
    }
    return fallback;
  }

  _zoneLabelSignature() {
    if (!this._hass?.states || !this._config?.entities) return "";
    return this._config.entities
      .map((eid) => {
        const k = this._trackerKeyFromEntity(eid);
        if (!this._entityOnThisFloor(k)) return "";
        return this._hass.states[`sensor.${k}_bps_zone`]?.state ?? "";
      })
      .join("|");
  }

  _floorPresenceSignature() {
    if (!this._hass?.states || !this._config?.entities) return "";
    return this._config.entities
      .map((eid) => {
        const k = this._trackerKeyFromEntity(eid);
        return this._hass.states[`sensor.${k}_bps_floor`]?.state ?? "";
      })
      .join("|");
  }

  _entityOnThisFloor(trackerKey) {
    const target = this._normalize(this._config.floor);
    const st = this._hass?.states?.[`sensor.${trackerKey}_bps_floor`]?.state;
    if (st == null || st === "unknown" || st === "unavailable") {
      return false;
    }
    return this._normalize(st) === target;
  }

  _prunePositionsByFloor() {
    for (const key of [...this._positions.keys()]) {
      if (!this._entityOnThisFloor(key)) {
        this._positions.delete(key);
      }
    }
  }

  _updateFloorStatus() {
    const tot = this._config.entities.length;
    const n = this._config.entities.filter((eid) =>
      this._entityOnThisFloor(this._trackerKeyFromEntity(eid)),
    ).length;
    this._setStatus(`Floor: ${this._config.floor} · ${n}/${tot} tracker(s) on this floor.`);
  }

  // Close JS approximation of homeassistant.util.slugify (python-slugify with
  // separator "_"): the same transform HA used to build the entity-id slugs
  // the receiver ids come from. Exact for Latin names; exotic unicode may
  // differ and simply falls through to the next status tier.
  static haSlugify(text) {
    if (!text) return "";
    let s = String(text).replace(/'+/g, "-");
    s = s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    return s
      .toLowerCase()
      .replace(/'+/g, "")
      .replace(/(\d),(?=\d)/g, "$1")
      .replace(/[^-a-z0-9]+/g, "-")
      .replace(/-{2,}/g, "-")
      .replace(/^-+|-+$/g, "")
      .replace(/-/g, "_");
  }

  // GET a /api/bps/* endpoint with the logged-in user's token attached (those
  // endpoints now require auth). Returns null (fires NO request) when there is
  // no valid token, while rate-backing-off after a recent auth failure, or once
  // a token has failed 5 times (a dead/revoked session must not keep feeding
  // HA's http.ban and get the IP banned). A different token clears all of that.
  // Callers treat a null / non-ok result as "no data this cycle".
  async _apiFetch(path) {
    const auth = this._hass && this._hass.auth;
    if (!auth) return null;
    // HA does not proactively refresh the access token for manual fetches (its
    // own use goes through fetchWithAuth); refresh it ourselves when expired so
    // we don't send a dead Bearer. Feature-detected and de-duplicated so a
    // burst of calls shares one refresh; on failure the guards below back off.
    try {
      if (auth.expired && typeof auth.refreshAccessToken === "function") {
        this._authRefresh = this._authRefresh
          || auth.refreshAccessToken().finally(() => { this._authRefresh = null; });
        await this._authRefresh;
      }
    } catch (e) { /* refresh failed: fall through to the backoff/dead-token guards */ }
    const token = auth.accessToken || (auth.data && auth.data.access_token);
    if (!token) return null;
    if (this._authDeadToken && token !== this._authDeadToken) {
      // Fresh credentials: retry immediately, dropping any pending backoff.
      this._authFails = 0; this._authBackoff = 0; this._authFailUntil = 0;
      this._authDeadToken = null;
    }
    if (token === this._authDeadToken && (this._authFails || 0) >= 5) return null; // dead token: silent
    if (Date.now() < (this._authFailUntil || 0)) return null;                      // rate backoff
    const res = await fetch(path, { headers: { Authorization: "Bearer " + token } });
    if (res.status === 401 || res.status === 403) {
      // Bounded backoff (5s -> 5min) AND a hard cap of attempts per token, so
      // failed auth can't keep hitting the ban tracker.
      this._authFails = (this._authFails || 0) + 1;
      this._authDeadToken = token;
      this._authBackoff = this._authBackoff ? Math.min(this._authBackoff * 2, 300000) : 5000;
      this._authFailUntil = Date.now() + this._authBackoff;
    } else {
      // Any non-401/403 response (incl. cords' normal "no fix yet" 404) proves
      // the Bearer was accepted: clear all auth-failure state.
      this._authFails = 0; this._authBackoff = 0; this._authFailUntil = 0;
      this._authDeadToken = null;
    }
    return res;
  }

  async _refreshBermudaScanners() {
    const hass = this._hass;
    if (!hass?.callWS || !this._config?.show_receivers) return;
    const now = Date.now();
    if (now < this._nextBermudaDumpAt) return;
    // Keep the refresh shorter than the offline threshold: between dumps a
    // scanner's age grows by the elapsed wall time, so a healthy scanner must
    // be re-anchored before it can cross receiver_timeout.
    this._nextBermudaDumpAt = now + Math.min(15, Math.max(5, this._config.receiver_timeout / 2)) * 1000;
    try {
      const resp = await hass.callWS({
        type: "call_service",
        domain: "bermuda",
        service: "dump_devices",
        service_data: { configured_devices: true },
        return_response: true,
      });
      const devices = resp?.response;
      if (!devices || typeof devices !== "object") return;
      // last_seen stamps are monotonic (seconds since HA host boot), not
      // epoch. The freshest stamp in the payload serves as "now" on that
      // clock — but only while adverts keep arriving.
      let newest = 0;
      for (const dev of Object.values(devices)) {
        const ls = dev?.last_seen;
        if (typeof ls === "number" && ls > newest) newest = ls;
      }
      // Re-anchor only when the payload aged forward. If no stamp advanced —
      // every scanner stopped hearing adverts, e.g. the only proxy wedged or
      // a fleet-wide outage — keep the previous map and anchor so ages keep
      // growing with wall time and cross receiver_timeout. A large backward
      // jump means the monotonic clock reset (HA reboot): accept it.
      if (this._bermudaScanners && newest <= this._bermudaNewest && newest > this._bermudaNewest - 60) {
        return;
      }
      this._bermudaNewest = newest;
      const bySlug = new Map();
      for (const dev of Object.values(devices)) {
        if (!dev || (dev._is_scanner !== true && dev.is_scanner !== true)) continue;
        const slug = BpsMapCard.haSlugify(dev.name);
        if (!slug) continue;
        const age = typeof dev.last_seen === "number" ? newest - dev.last_seen : Infinity;
        bySlug.set(slug, age);
      }
      this._bermudaScanners = bySlug;
      this._bermudaDumpAt = now;
    } catch (e) {
      // Bermuda missing, too old for service response data, or a transient
      // websocket error. Keep any previously working map — wall-clock aging
      // degrades it gracefully toward offline — and back off harder only
      // when the tier never worked.
      this._nextBermudaDumpAt = now + (this._bermudaScanners ? 60000 : 300000);
    }
  }

  // Availability of the HA device whose name slug matches the receiver id:
  // true/false when the device was found and has states, null to fall through.
  _deviceOnlineBySlug(receiverId) {
    const devices = this._hass?.devices;
    const entities = this._hass?.entities;
    const states = this._hass?.states;
    if (!devices || !entities || !states) return null;
    if (this._devicesRef !== devices) {
      this._devicesRef = devices;
      this._deviceSlugMap = new Map();
      const ambiguous = new Set();
      for (const dev of Object.values(devices)) {
        const slug = BpsMapCard.haSlugify(dev?.name_by_user || dev?.name);
        if (!slug) continue;
        if (this._deviceSlugMap.has(slug)) ambiguous.add(slug);
        else this._deviceSlugMap.set(slug, dev.id);
      }
      // Two devices with the same name slug: picking one would be a guess.
      for (const slug of ambiguous) this._deviceSlugMap.delete(slug);
    }
    if (this._entitiesRef !== entities) {
      this._entitiesRef = entities;
      this._deviceEntitiesMap = new Map();
      for (const [entityId, ent] of Object.entries(entities)) {
        if (!ent?.device_id) continue;
        let list = this._deviceEntitiesMap.get(ent.device_id);
        if (!list) this._deviceEntitiesMap.set(ent.device_id, (list = []));
        list.push(entityId);
      }
    }
    const deviceId = this._deviceSlugMap.get(receiverId);
    if (!deviceId) return null;
    const entityIds = this._deviceEntitiesMap.get(deviceId);
    if (!entityIds || entityIds.length === 0) return null;
    // A connectivity sensor is authoritative: ESPHome's status sensor stays
    // available with state "off" when the device dies, so its state — not its
    // mere availability — decides, and it must be checked before any other
    // entity can count as proof of life.
    for (const entityId of entityIds) {
      const stateObj = states[entityId];
      if (stateObj?.state != null && stateObj.attributes?.device_class === "connectivity") {
        return BpsMapCard.stateLooksOnline(stateObj.state);
      }
    }
    let sawState = false;
    for (const entityId of entityIds) {
      const st = states[entityId]?.state;
      if (st == null) continue;
      sawState = true;
      if (st !== "unavailable") return true;
    }
    return sawState ? false : null;
  }

  static stateLooksOnline(state) {
    if (state == null) return false;
    const s = String(state).trim().toLowerCase();
    return !["", "unavailable", "unknown", "none", "off", "false", "not_home", "offline", "disconnected"].includes(s);
  }

  _computeReceiverStatuses() {
    const statuses = new Map();
    const states = this._hass?.states;
    if (!this._config?.show_receivers || !states || this._receivers.length === 0) {
      return statuses;
    }
    const heuristic = [];
    for (const rec of this._receivers) {
      const id = rec.entity_id;
      const statusEntity = this._config.receiver_status[id];
      if (statusEntity === false || statusEntity === "heuristic") {
        // Explicit opt-out from the status sensor: the ESPHome status
        // platform only reports API connectivity, so a proxy whose BLE stack
        // has wedged still reads "on"; this forces the distance heuristic.
        statuses.set(id, false);
        heuristic.push({ id, suffix: `_distance_to_${id}` });
        continue;
      }
      if (statusEntity) {
        statuses.set(id, BpsMapCard.stateLooksOnline(states[statusEntity]?.state));
        continue;
      }
      // Bermuda's own scanner liveness: last advertisement heard within
      // receiver_timeout seconds. Ages were anchored when the dump was
      // fetched, so add the wall time elapsed since.
      if (this._bermudaScanners) {
        const ageAtDump = this._bermudaScanners.get(id);
        if (ageAtDump != null) {
          const age = ageAtDump + (Date.now() - this._bermudaDumpAt) / 1000;
          statuses.set(id, age <= this._config.receiver_timeout);
          continue;
        }
      }
      // The conventional ESPHome status sensor. This must run BEFORE the
      // generic device-availability tier: ESPHome keeps this sensor available
      // with state "off" when the device disconnects, so "any entity not
      // unavailable" would report a dead proxy as online. Require the
      // connectivity device_class so an unrelated entity that merely shares
      // the binary_sensor.<id>_status slug does not hijack the status.
      const autoStatus = states[`binary_sensor.${id}_status`];
      if (autoStatus && autoStatus.attributes?.device_class === "connectivity") {
        statuses.set(id, BpsMapCard.stateLooksOnline(autoStatus.state));
        continue;
      }
      // The receiver's HA device: online while any of its entities has a
      // state other than unavailable.
      const deviceOnline = this._deviceOnlineBySlug(id);
      if (deviceOnline != null) {
        statuses.set(id, deviceOnline);
        continue;
      }
      statuses.set(id, false);
      heuristic.push({ id, suffix: `_distance_to_${id}` });
    }
    if (heuristic.length > 0) {
      // A receiver is working when at least one tracker got a distance
      // reading through it within Bermuda's ~30 s distance timeout.
      for (const entityId of Object.keys(states)) {
        if (!entityId.startsWith("sensor.") || !entityId.includes("_distance_to_")) continue;
        const st = states[entityId]?.state;
        if (st == null || st === "unknown" || st === "unavailable") continue;
        for (const { id, suffix } of heuristic) {
          if (!statuses.get(id) && entityId.endsWith(suffix)) {
            statuses.set(id, true);
          }
        }
      }
    }
    return statuses;
  }

  _markerLabelText(trackerKey, pos) {
    if (this._config.zone_label) {
      const zoneEnt = `sensor.${trackerKey}_bps_zone`;
      const st = this._hass?.states?.[zoneEnt]?.state;
      if (st && st !== "unknown" && st !== "unavailable") {
        return st;
      }
      if (pos && pos.zone != null && String(pos.zone).trim() !== "") {
        return String(pos.zone);
      }
      return "unknown";
    }
    if (pos && pos.label) return pos.label;
    return this._friendlyLabel(trackerKey);
  }

  _trackerIconUrl(trackerKey) {
    const DEFAULT_TRACKER_ICON = "/bps/person.svg";
    const storedIcon = this._trackerIcons?.[trackerKey];
    if (storedIcon === "person.svg") return "/bps/person.svg";
    if (storedIcon === "beacon.svg") return "/bps/beacon.svg";
    return storedIcon || DEFAULT_TRACKER_ICON;
  }

  _getIconImage(url) {
    if (!url) return null;
    const cached = this._iconCache.get(url);
    if (cached) return cached;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => this._redraw();
    img.src = url;
    this._iconCache.set(url, img);
    return img;
  }

  _tintedIcon(url, color, sizePx) {
    const img = this._getIconImage(url);
    if (!img || !img.complete || img.naturalWidth === 0) return null;
    const size = Math.max(8, Math.round(sizePx));
    const key = `${url}|${color}|${size}`;
    const cached = this._tintedIconCache.get(key);
    if (cached) return cached;
    const off = document.createElement("canvas");
    off.width = size;
    off.height = size;
    const octx = off.getContext("2d");
    octx.drawImage(img, 0, 0, size, size);
    octx.globalCompositeOperation = "source-in";
    octx.fillStyle = color;
    octx.fillRect(0, 0, size, size);
    this._tintedIconCache.set(key, off);
    return off;
  }

  async _bootstrap(expectedGen) {
    try {
      await this._loadFloorResources(expectedGen);
      if (expectedGen !== this._runGeneration) {
        return;
      }
      this._redraw();
      this._updateFloorStatus();
    } catch (e) {
      console.error(e);
      this._setStatus(e.message || String(e));
      // The one-shot bootstrap otherwise never retries (set hass only
      // re-bootstraps when _bootstrapPromise is falsy). Now that read_text /
      // maps require auth, a transient 401/network blip here would leave the
      // card permanently broken. Re-arm after a delay so a later hass update
      // retries — throttled so a persistent failure can't hammer the endpoint.
      setTimeout(() => { this._bootstrapPromise = null; }, 15000);
    }
  }

  _trackerKeyFromEntity(entityId) {
    if (!entityId || typeof entityId !== "string") return "";
    return entityId.replace(/^sensor\./, "");
  }

  _normalize(value) {
    return String(value || "").trim().toLowerCase();
  }

  async _loadFloorResources(expectedGen) {
    const res = await this._apiFetch("/api/bps/read_text");
    if (!res) throw new Error("BPS auth not ready (no token / backing off)");
    if (!res.ok) throw new Error(`Could not read BPS data (${res.status})`);
    if (expectedGen !== this._runGeneration) {
      return;
    }
    const data = await res.json();
    if (expectedGen !== this._runGeneration) {
      return;
    }
    const coords = JSON.parse(data.coordinates);
    this._trackerIcons = coords.tracker_icons && typeof coords.tracker_icons === "object"
      ? coords.tracker_icons
      : {};
    const requestedFloor = this._normalize(this._config.floor);
    const floor = coords.floor.find((f) => this._normalize(f.name) === requestedFloor);
    if (!floor) {
      throw new Error(`No floor found with the name "${this._config.floor}".`);
    }
    this._receivers = Array.isArray(floor.receivers)
      ? floor.receivers.filter((r) => r && r.entity_id && r.cords && r.cords.x != null && r.cords.y != null)
      : [];
    this._subzones = Array.isArray(floor.subzones)
      ? floor.subzones.filter((s) => s && Array.isArray(s.cords) && s.cords.length >= 3)
      : [];
    this._zones = Array.isArray(floor.zones)
      ? floor.zones.filter((z) => z && Array.isArray(z.cords) && z.cords.length >= 3)
      : [];
    await this._refreshBermudaScanners();
    this._receiverStatuses = this._computeReceiverStatuses();
    if (expectedGen !== this._runGeneration) {
      return;
    }
    const mapUrl = await this._resolveMapUrl(floor.name);
    if (mapUrl !== this._mapUrlLoaded || !this._baseImage) {
      await this._loadFloorImage(mapUrl, expectedGen);
      if (expectedGen !== this._runGeneration) {
        return;
      }
      this._mapUrlLoaded = mapUrl;
    }
  }

  async _resolveMapUrl(resolvedFloorName) {
    if (this._config.image) return this._config.image;
    const explicitMap = String(this._config.map_file || "").trim();
    if (explicitMap) {
      return `/local/bps_maps/${explicitMap}`;
    }

    const floorName = String(resolvedFloorName || this._config.floor || "").trim();
    const mapsRes = await this._apiFetch("/api/bps/maps");
    if (!mapsRes) throw new Error("BPS auth not ready (no token / backing off)");
    if (!mapsRes.ok) {
      throw new Error(
        `Could not list map files (${mapsRes.status}). Set map_file explicitly or check /api/bps/maps.`,
      );
    }
    const maps = await mapsRes.json();
    if (!Array.isArray(maps) || maps.length === 0) {
      throw new Error("No map files found in /local/bps_maps.");
    }

    const normalizedFloor = this._normalize(floorName);
    const exactName = maps.find((m) => this._normalize(m) === normalizedFloor);
    if (exactName) {
      return `/local/bps_maps/${exactName}`;
    }

    const byBaseName = maps.find((m) => {
      const base = String(m).replace(/\.[^/.]+$/, "");
      return this._normalize(base) === normalizedFloor;
    });
    if (byBaseName) {
      return `/local/bps_maps/${byBaseName}`;
    }

    throw new Error(
      `No map image matched floor "${floorName}". Add map_file, image, or rename a file in /local/bps_maps.`,
    );
  }

  _loadFloorImage(url, expectedGen) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        if (expectedGen !== this._runGeneration) {
          resolve();
          return;
        }
        this._baseImage = img;
        this._imgNaturalW = img.naturalWidth;
        this._imgNaturalH = img.naturalHeight;
        resolve();
      };
      img.onerror = () => reject(new Error(`Could not load floor image: ${url}`));
      img.src = url;
    });
  }

  _resizeCanvasToImage() {
    if (!this._baseImage) return;
    const ratio = this._baseImage.naturalHeight / this._baseImage.naturalWidth;
    const w = this._coordinateWidth;
    const h = Math.round(w * ratio);
    if (this._canvas.width !== w || this._canvas.height !== h) {
      this._canvas.width = w;
      this._canvas.height = h;
    }
    this._imgNaturalW = w;
    this._imgNaturalH = h;
    this._canvas.style.aspectRatio = `${w} / ${h}`;
  }

  _drawBase() {
    if (!this._baseImage) return;
    this._resizeCanvasToImage();
    const ctx = this._canvas.getContext("2d");
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    // Keep the exact same coordinate space as the sidebar panel (normalized 2000px width).
    ctx.drawImage(this._baseImage, 0, 0, this._canvas.width, this._canvas.height);
  }

  _drawMarkers() {
    if (!this._imgNaturalW) return;
    const ctx = this._canvas.getContext("2d");
    const minSide = Math.min(this._canvas.width, this._canvas.height);
    const baseIconSize = Math.max(12, minSide * 0.04);
    const iconSize = baseIconSize * (this._config.scale_icon / 100);
    ctx.save();
    for (const [trackerKey, pos] of this._positions) {
      if (pos == null || pos.x == null || pos.y == null) continue;
      if (!this._entityOnThisFloor(trackerKey)) continue;
      const iconUrl = this._trackerIconUrl(trackerKey);
      const iconImg = this._getIconImage(iconUrl);
      if (iconImg && iconImg.complete && iconImg.naturalWidth > 0) {
        ctx.drawImage(iconImg, pos.x - iconSize / 2, pos.y - iconSize / 2, iconSize, iconSize);
      } else {
        ctx.beginPath();
        ctx.fillStyle = "rgba(33, 150, 243, 0.85)";
        ctx.strokeStyle = "#0d47a1";
        ctx.lineWidth = 2;
        ctx.arc(pos.x, pos.y, iconSize / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      if (this._config.show_labels) {
        const text = this._markerLabelText(trackerKey, pos);
        if (text) {
          const scale = this._config.scale_labels / 100;
          const fontPx = Math.max(11, iconSize * 0.35) * scale;
          ctx.font = `bold ${fontPx}px sans-serif`;
          ctx.fillStyle = "#111";
          // Right of the icon; flipped to the left side when it would run
          // off the canvas edge.
          const textWidth = ctx.measureText(text).width;
          let labelX = pos.x + iconSize / 2 + 4;
          if (labelX + textWidth > this._canvas.width - 2) {
            labelX = pos.x - iconSize / 2 - 4 - textWidth;
          }
          ctx.fillText(text, Math.max(2, labelX), pos.y + iconSize * 0.12);
        }
      }
    }
    ctx.restore();
  }

  _drawSubZones() {
    if (!this._config?.show_sub_zones || !this._imgNaturalW) return;
    const subs = this._subzones || [];
    if (!subs.length) return;
    const ctx = this._canvas.getContext("2d");
    ctx.save();
    for (const sub of subs) {
      const pts = sub.cords || [];
      if (pts.length < 3) continue;
      const color = sub.color || "#3f51b5";
      ctx.beginPath();
      ctx.moveTo(Number(pts[0].x), Number(pts[0].y));
      for (let i = 1; i < pts.length; i++) ctx.lineTo(Number(pts[i].x), Number(pts[i].y));
      ctx.closePath();
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.restore();
  }

  _drawReceivers() {
    if (!this._config?.show_receivers || !this._imgNaturalW || this._receivers.length === 0) return;
    const ctx = this._canvas.getContext("2d");
    const minSide = Math.min(this._canvas.width, this._canvas.height);
    const baseIconSize = Math.max(12, minSide * 0.04);
    const iconSize = baseIconSize * (this._config.scale_receiver_icon / 100);
    const ONLINE_COLOR = "#000000";
    const OFFLINE_COLOR = "#d32f2f";
    ctx.save();
    for (const rec of this._receivers) {
      const x = Number(rec.cords.x);
      const y = Number(rec.cords.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      const online = this._receiverStatuses.get(rec.entity_id) === true;
      const color = online ? ONLINE_COLOR : OFFLINE_COLOR;
      const icon = this._tintedIcon("/bps/beacon.svg", color, iconSize);
      if (icon) {
        ctx.drawImage(icon, x - iconSize / 2, y - iconSize / 2, iconSize, iconSize);
      } else {
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.arc(x, y, iconSize / 2, 0, Math.PI * 2);
        ctx.fill();
      }
      if (this._config.show_receiver_labels) {
        const scale = this._config.scale_receiver_labels / 100;
        const fontPx = Math.max(11, iconSize * 0.35) * scale;
        ctx.font = `bold ${fontPx}px sans-serif`;
        ctx.fillStyle = color;
        // Centered under the icon, clamped to the canvas so names near the
        // edges stay fully readable; flipped above the icon at the bottom.
        const textWidth = ctx.measureText(rec.entity_id).width;
        let labelX = x - textWidth / 2;
        labelX = Math.max(2, Math.min(this._canvas.width - textWidth - 2, labelX));
        let labelY = y + iconSize / 2 + fontPx;
        if (labelY > this._canvas.height - 2) {
          labelY = y - iconSize / 2 - fontPx * 0.4;
        }
        ctx.fillText(rec.entity_id, labelX, labelY);
      }
    }
    ctx.restore();
  }

  _redraw() {
    this._drawBase();
    this._drawSubZones();
    this._drawZoneLabels();
    this._drawReceivers();
    this._drawMarkers();
  }

  // Average of a polygon's vertices — good enough for placing a centered label,
  // and order-independent so it matches the panel for both polygon zones and
  // legacy 4-point (scan-order) rectangles.
  _polygonCentroid(cords) {
    if (!Array.isArray(cords) || cords.length < 3) return null;
    let sx = 0;
    let sy = 0;
    let n = 0;
    for (const p of cords) {
      const x = Number(p.x);
      const y = Number(p.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      sx += x;
      sy += y;
      n++;
    }
    if (n === 0) return null;
    return { x: sx / n, y: sy / n };
  }

  // Bounding box of a centered label (textAlign=center, textBaseline=middle).
  _labelBox(ctx, text, cx, cy, fontPx) {
    const w = ctx.measureText(text).width;
    const h = fontPx;
    return { left: cx - w / 2, right: cx + w / 2, top: cy - h / 2, bottom: cy + h / 2, h };
  }

  _boxesOverlap(a, b) {
    return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  }

  // White halo (stroke) then colored fill, so a name stays legible over the
  // map. strokeStyle/lineWidth/font/alignment are set by the caller.
  _drawHaloText(ctx, text, x, y, color) {
    ctx.strokeText(text, x, y);
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
  }

  // Zone names at their centers; sub-zone names at their centers too, but
  // nudged clear of any zone label they would overlap (a sub-zone sits inside a
  // zone, so its center is often near the zone's).
  _drawZoneLabels() {
    if (!this._config?.show_zone_labels || !this._imgNaturalW) return;
    const zones = this._zones || [];
    const subs = this._subzones || [];
    if (!zones.length && !subs.length) return;
    const ctx = this._canvas.getContext("2d");
    const minSide = Math.min(this._canvas.width, this._canvas.height);
    const labelScale = this._config.scale_labels / 100;
    const zoneFont = Math.max(12, minSide * 0.028) * labelScale;
    const subFont = Math.max(11, minSide * 0.022) * labelScale;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.lineJoin = "round";

    // Zone labels first; remember their boxes so sub-zone labels can dodge them.
    const zoneBoxes = [];
    ctx.font = `600 ${zoneFont}px system-ui, sans-serif`;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = Math.max(2, zoneFont * 0.18);
    for (const zone of zones) {
      const text = zone.entity_id;
      if (!text) continue;
      const c = this._polygonCentroid(zone.cords);
      if (!c) continue;
      // Clamp the center so an edge-adjacent room keeps its whole name on the
      // canvas (same intent as the receiver/marker label routines).
      const halfW = ctx.measureText(text).width / 2;
      const cx = Math.max(halfW + 2, Math.min(this._canvas.width - halfW - 2, c.x));
      const cy = Math.max(zoneFont / 2 + 2, Math.min(this._canvas.height - zoneFont / 2 - 2, c.y));
      this._drawHaloText(ctx, text, cx, cy, "#d32f2f");
      zoneBoxes.push(this._labelBox(ctx, text, cx, cy, zoneFont));
    }

    // Sub-zone labels in their own color, pushed past any overlapping zone label.
    ctx.font = `600 ${subFont}px system-ui, sans-serif`;
    ctx.lineWidth = Math.max(2, subFont * 0.18);
    for (const sub of subs) {
      const text = sub.entity_id;
      if (!text) continue;
      const c = this._polygonCentroid(sub.cords);
      if (!c) continue;
      const halfW = ctx.measureText(text).width / 2;
      const cx = Math.max(halfW + 2, Math.min(this._canvas.width - halfW - 2, c.x));
      let y = c.y;
      let box = this._labelBox(ctx, text, cx, y, subFont);
      const gap = subFont * 0.35;
      let guard = 0;
      // Shift away from each zone label it hits (below if the sub-zone sits at
      // or under the zone label, above otherwise) until it clears them.
      while (guard < 10) {
        const hit = zoneBoxes.find((zb) => this._boxesOverlap(zb, box));
        if (!hit) break;
        if (y >= (hit.top + hit.bottom) / 2) {
          y = hit.bottom + box.h / 2 + gap;
        } else {
          y = hit.top - box.h / 2 - gap;
        }
        box = this._labelBox(ctx, text, cx, y, subFont);
        guard++;
      }
      // Keep the (possibly nudged) label on-canvas vertically.
      y = Math.max(box.h / 2 + 2, Math.min(this._canvas.height - box.h / 2 - 2, y));
      this._drawHaloText(ctx, text, cx, y, sub.color || "#3f51b5");
    }
    ctx.restore();
  }

  _startPolling() {
    this._stopPolling();
    const ms = this._config.poll_interval * 1000;
    this._pollTimer = window.setInterval(() => this._pollOnce(), ms);
    this._pollOnce();
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _pollOnce() {
    try {
      // A 404 here just means no tracker has position data yet; receivers
      // should still render, so this is not an early return.
      const res = await this._apiFetch("/api/bps/cords");
      if (res && res.ok) {
        const list = await res.json();
        if (Array.isArray(list)) {
          for (const ent of this._config.entities) {
            const key = this._trackerKeyFromEntity(ent);
            if (!this._entityOnThisFloor(key)) {
              this._positions.delete(key);
              continue;
            }
            const row = list.find((item) => item.ent === key);
            if (row && Array.isArray(row.cords) && row.cords.length >= 2) {
              this._positions.set(key, {
                x: row.cords[0],
                y: row.cords[1],
                label: this._friendlyLabel(key),
                zone: row.zone != null ? row.zone : "",
              });
            }
          }
        }
      }
      if (this._config.show_receivers) {
        await this._refreshBermudaScanners();
        this._receiverStatuses = this._computeReceiverStatuses();
      }
      this._redraw();
      if (this._baseImage) {
        // Without a base image the bootstrap error in the status line is the
        // only hint at what went wrong; keep it visible.
        this._updateFloorStatus();
      }
    } catch (e) {
      console.warn("BPS poll:", e);
    }
  }

}

customElements.define("bps-map-card", BpsMapCard);

class BpsMapCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._inputs = {};
    this._built = false;
  }

  setConfig(config) {
    this._config = { ...config };
    this._config.scale_labels = BpsMapCard.normalizePercent(this._config.scale_labels);
    this._config.scale_icon = BpsMapCard.normalizePercent(this._config.scale_icon);
    this._render();
  }

  set hass(hass) {
    // Store only. Re-rendering here on every HA state update (which fires
    // constantly) would tear down and rebuild the inputs mid-edit — stealing
    // focus from a text field being typed in and dropping clicks on checkboxes.
    this._hass = hass;
  }

  _render() {
    // Build the DOM once, then only sync values on later config updates. HA
    // re-sets the config after each of our own change events (and on every
    // state tick via `hass`), so rebuilding here would destroy the input the
    // user is interacting with.
    if (this._built) {
      this._syncValues();
      return;
    }
    this.innerHTML = "";
    this._inputs = {};
    const root = document.createElement("div");
    root.style.padding = "8px";

    const mk = (label, key, type = "text", placeholder = "") => {
      const row = document.createElement("div");
      row.style.marginBottom = "8px";
      const l = document.createElement("label");
      l.textContent = label;
      l.style.display = "block";
      l.style.fontSize = "12px";
      const inp = document.createElement("input");
      inp.type = type;
      inp.placeholder = placeholder;
      if (type === "checkbox") {
        inp.checked = Boolean(this._config[key]);
      } else {
        inp.style.width = "100%";
        inp.value = this._config[key] != null ? this._config[key] : "";
      }
      inp.addEventListener("change", () => {
        if (type === "number") {
          // A cleared or non-positive field means "unset" (inherit/default),
          // not 0 — every number option coerces to a default at setConfig.
          const n = Number(inp.value);
          if (inp.value.trim() === "" || !Number.isFinite(n) || n <= 0) delete this._config[key];
          else this._config[key] = n;
        } else if (type === "checkbox") this._config[key] = inp.checked;
        else this._config[key] = inp.value;
        this._fire();
      });
      row.appendChild(l);
      row.appendChild(inp);
      root.appendChild(row);
      this._inputs[key] = inp;
    };

    mk("Floor (floor name)", "floor", "text", "MyFloor");

    const entRow = document.createElement("div");
    entRow.style.marginBottom = "8px";
    const entLabel = document.createElement("label");
    entLabel.textContent = "Entities (comma separated sensor.*)";
    entLabel.style.display = "block";
    entLabel.style.fontSize = "12px";
    const entInp = document.createElement("input");
    entInp.type = "text";
    entInp.style.width = "100%";
    entInp.placeholder = "sensor.phone_alice, sensor.phone_bob";
    entInp.value = Array.isArray(this._config.entities) ? this._config.entities.join(", ") : "";
    entInp.addEventListener("change", () => {
      this._config.entities = entInp.value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      this._fire();
    });
    entRow.appendChild(entLabel);
    entRow.appendChild(entInp);
    root.appendChild(entRow);
    this._inputs.entities = entInp;

    mk("Map file (optional, filename in www/bps_maps)", "map_file", "text", "floor.png");
    mk("Image URL (optional, overrides map file)", "image", "text", "https://...");
    mk("Poll interval (seconds)", "poll_interval", "number", "3");
    mk("Label scale (percent, e.g. 100 or 200)", "scale_labels", "number", "100");
    mk("Icon scale (percent, e.g. 100 or 200)", "scale_icon", "number", "100");
    mk("Receiver icon scale (percent, empty = icon scale)", "scale_receiver_icon", "number", "");
    mk("Receiver label scale (percent, empty = label scale)", "scale_receiver_labels", "number", "");
    mk("Receiver timeout (seconds without adverts, min 10, default 30)", "receiver_timeout", "number", "30");

    mk("Show labels", "show_labels", "checkbox");
    mk("Show zone instead of device name", "zone_label", "checkbox");
    mk("Show zone / sub-zone labels", "show_zone_labels", "checkbox");
    mk("Show receivers (black = working, red = offline)", "show_receivers", "checkbox");
    mk("Show receiver labels", "show_receiver_labels", "checkbox");
    mk("Show sub-zones", "show_sub_zones", "checkbox");

    this.appendChild(root);
    this._built = true;
  }

  // Push the current config values into the already-built inputs without
  // rebuilding them, so nothing loses focus. The input being edited is left
  // alone.
  _syncValues() {
    // The editor lives in Home Assistant's shadow DOM, where
    // document.activeElement retargets to the shadow host and never equals our
    // inner input. Ask the editor's own root (shadow root or document) for the
    // focused node so a field being edited is genuinely left alone.
    const activeEl = this.getRootNode().activeElement;
    for (const [key, inp] of Object.entries(this._inputs)) {
      if (inp === activeEl) continue;
      if (inp.type === "checkbox") {
        inp.checked = Boolean(this._config[key]);
      } else if (key === "entities") {
        inp.value = Array.isArray(this._config.entities) ? this._config.entities.join(", ") : "";
      } else {
        inp.value = this._config[key] != null ? this._config[key] : "";
      }
    }
  }

  _fire() {
    this._config.scale_labels = BpsMapCard.normalizePercent(this._config.scale_labels);
    this._config.scale_icon = BpsMapCard.normalizePercent(this._config.scale_icon);
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

customElements.define("bps-map-card-editor", BpsMapCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "bps-map-card",
  name: "BPS Map",
  description: "Show one or more BPS trackers on a floor plan.",
  preview: true,
  documentationURL: "https://github.com/maxi1134/BPS-improved",
});

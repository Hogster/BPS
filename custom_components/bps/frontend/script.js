document.addEventListener('DOMContentLoaded', async () => {
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');

    // --- API auth token (see bps-panel.js) ---------------------------------
    // The BPS panel element couriers the HA access token in via postMessage;
    // every /api/bps/* call goes through bpsFetch(), which attaches it as a
    // Bearer header (those endpoints now require auth). API calls hold until
    // the first token arrives so none fire unauthenticated — but never block
    // forever: if the app is opened outside the panel, calls proceed after a
    // short wait and 401 visibly rather than hanging.
    let bpsAuthToken = null;
    let _resolveToken = null;
    const _tokenReady = new Promise((resolve) => { _resolveToken = resolve; });
    const _settleToken = () => { if (_resolveToken) { _resolveToken(); _resolveToken = null; } };
    // Auth-failure handling: after a 401/403 we back off (5s -> 5min) AND cap
    // the number of attempts per token, so a stale/expired/revoked token can't
    // keep racking up failed-auth hits and get our IP banned by HA's http.ban.
    // A fresh token couriered in from the panel clears all of it immediately.
    let _authFailUntil = 0;
    let _authBackoff = 0;
    let _authFails = 0;
    let _authDeadToken = null;
    window.addEventListener("message", (e) => {
        if (e.origin !== window.location.origin) return;
        if (e.data && e.data.type === "bps-auth" && e.data.token) {
            const isNew = e.data.token !== bpsAuthToken;
            bpsAuthToken = e.data.token;
            if (isNew) { _authFailUntil = 0; _authBackoff = 0; _authFails = 0; _authDeadToken = null; } // fresh token: retry now
            _settleToken();
        }
    });
    if (window.parent && window.parent !== window) {
        window.parent.postMessage("bps-ready", window.location.origin);
    }
    setTimeout(_settleToken, 5000);

    async function bpsFetch(url, opts = {}) {
        if (bpsAuthToken === null) await _tokenReady;
        // Dead token: after 5 failures on this exact token, send nothing more
        // with it until a different one is couriered in. The 503 is treated by
        // callers as "no data this cycle".
        if (bpsAuthToken && bpsAuthToken === _authDeadToken && _authFails >= 5) {
            return new Response(null, { status: 503, statusText: "BPS auth stuck" });
        }
        // Rate backoff between the allowed attempts.
        if (Date.now() < _authFailUntil) {
            return new Response(null, { status: 503, statusText: "BPS auth backoff" });
        }
        const headers = Object.assign({}, opts.headers || {});
        if (bpsAuthToken) headers["Authorization"] = "Bearer " + bpsAuthToken;
        const res = await fetch(url, Object.assign({}, opts, { headers }));
        if (res.status === 401 || res.status === 403) {
            _authFails += 1;
            _authDeadToken = bpsAuthToken;
            _authBackoff = _authBackoff ? Math.min(_authBackoff * 2, 300000) : 5000;
            _authFailUntil = Date.now() + _authBackoff;
            // Ask the panel for a fresh token: it refreshes an expired one and
            // couriers it back, which clears this state (message handler above).
            if (window.parent && window.parent !== window) {
                window.parent.postMessage("bps-ready", window.location.origin);
            }
        } else {
            // Any non-401/403 response (incl. cords' normal 404) proves the
            // Bearer was accepted: clear all auth-failure state.
            _authFails = 0;
            _authBackoff = 0;
            _authFailUntil = 0;
            _authDeadToken = null;
        }
        return res;
    }
    const upload = document.getElementById('upload');
    const mapSelector = document.getElementById('mapSelector');
    const entSelector = document.getElementById('entSelector');
    const trackerIconSelector = document.getElementById('trackerIconSelector');
    const trackerIconUpload = document.getElementById('trackerIconUpload');
    const uploadTrackerIconButton = document.getElementById('uploadTrackerIcon');
    const mapbuttondiv = document.getElementById('mapbuttondiv');
    const savebuttondiv = document.getElementById('savebuttondiv');
    const trackdiv = document.getElementById('trackdiv');
    const zonediv = document.getElementById('zonediv');
    const messdiv = document.getElementById('message');
    const saveButton = document.createElement('button');

    //Delete button
    const deleteButton = document.createElement('button');
    deleteButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&amp;_svg]:pointer-events-none [&amp;_svg]:size-4 [&amp;_svg]:shrink-0 text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2';
    deleteButton.style = 'background-color: red';
    deleteButton.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-save w-4 h-4 mr-2" data-component-name="Save"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"></path><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"></path><path d="M7 3v4a1 1 0 0 0 1 1h7"></path></svg>
            Delete Floor
        `;

    const mapname = document.getElementById('mapname');
    const starttrackbtn = document.getElementById('starttrack');
    const stoptrackbtn = document.getElementById('stoptrack');
    const circleControl = document.getElementById('circleControl');
    const traceControl = document.getElementById('traceControl');
    const cancelToolBtn = document.getElementById('cancelToolBtn');
    const saveToolBtn = document.getElementById('saveToolBtn');
    const mapToolActions = document.getElementById('mapToolActions');
    const zoneColorsToggle = document.getElementById('zoneColorsToggle');
    const drawAreaButton = document.createElement('button');
    const drawSubZoneButton = document.createElement('button');
    const addDeviceButton = document.createElement('button');
    const clearCanvasButton = document.createElement('button');
    const saveReceiverButton = document.createElement('button');
    const SetScaleButton = document.createElement('button');
    const adjustZonesButton = document.createElement('button');
    const adjustSubZonesButton = document.createElement('button');
    let img = new Image();
    let tmpcords = null;
    let finalcords = {
        floor: [] // Array to manage multiple floors
      };
    let tmpfinalcords = [];
    // Active "Adjust zones" preview: {zones, subzones, changes, warnings, options,
    // snapshot} or null. While set, drawElements overlays the proposed zones as a
    // green dashed ghost; finalcords is not mutated until Apply.
    let adjustPreview = null;
    let adjustTarget = 'zones'; // 'zones' or 'subzones' — which set the open preview adjusts
    let adjustRunSeq = 0; // bumped to invalidate in-flight preview requests
    // Array to store circles
    const circles = [];
    let receiverName = "";
    let receiverOptions = []; // Receiver names known from Bermuda sensors
    let offlineReceivers = []; // scanners Bermuda hasn't heard recently (backend liveness poll)
    // Naming-mismatch diagnostics from read_text (issue #64): placed receivers
    // with no matching Bermuda sensor (each with a suggested live scanner), and
    // scanners reporting a distance that aren't placed anywhere.
    let scannerDiagnostics = { unmatched_receivers: [], unplaced_scanners: [] };
    // Receiver-linking snapshot from /api/bps/scanner_linking (issue #64): every
    // placed receiver with its Bermuda distance sensors + live states. Feeds the
    // full Debugging tab and the compact "not reporting" heads-up in the map
    // sidebar. Refreshed on load, on Refresh, and when the Debugging tab opens.
    let scannerLinkingLoading = false;
    let scannerLinkingData = null;
    let debugSubtab = "receivers"; // Debugging tab sub-view: "receivers" | "beacons"
    // A placed receiver is "offline" when its scanner's distance sensors are
    // gone (slug no longer in the reported list) OR Bermuda hasn't heard the
    // scanner recently (backend liveness). Guarded on the list being loaded so
    // nothing is flagged before the receiver data arrives.
    function isReceiverOffline(slug) {
        if (receiverOptions.length === 0) return false;
        return !receiverOptions.includes(slug) || offlineReceivers.includes(slug);
    }

    // Live-refresh the offline set from the backend so (Offline) markers update
    // without a reload. Repaints only when the set changed and we're not mid
    // draw/edit (would wipe the overlay) or mid-tracking (that loop repaints and
    // picks up the new set on its own).
    async function fetchReceiverStatus() {
        try {
            const res = await bpsFetch('/api/bps/receiver_status');
            if (!res.ok) return;
            const data = await res.json();
            const next = Array.isArray(data.offline) ? data.offline : [];
            const changed = next.length !== offlineReceivers.length
                || next.some(s => !offlineReceivers.includes(s));
            offlineReceivers = next;
            if (changed && mapReady() && !drawToolActive() && !editTarget && !pollTrackActive) {
                clearCanvas();
                drawElements();
            }
        } catch (e) { /* transient; keep the last known set */ }
    }
    setInterval(fetchReceiverStatus, 10000);
    let zoneName = "";
    // Floor names come from two places that can disagree in case/whitespace:
    // the typed floor-name field and the map file basename. Always compare
    // them normalized (the map card does the same).
    const sameFloorName = (a, b) =>
        String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
    // Receiver/zone ids can be user-typed (Custom name…); never trust them in HTML.
    const escHtml = s => String(s).replace(/[&<>"']/g,
        c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // Map viewport: zoom/pan applied as one canvas transform. All stored
    // coordinates stay in the fixed 2000px-wide world space; only rendering
    // and mouse conversion go through the view.
    const view = { zoom: 1, x: 0, y: 0 };

    function clampView() {
        view.zoom = Math.max(1, Math.min(8, view.zoom));
        view.x = Math.max(canvas.width * (1 - view.zoom), Math.min(0, view.x));
        view.y = Math.max(canvas.height * (1 - view.zoom), Math.min(0, view.y));
    }

    function worldFromEvent(event) {
        const rect = canvas.getBoundingClientRect();
        const px = (event.clientX - rect.left) * (canvas.width / rect.width);
        const py = (event.clientY - rect.top) * (canvas.height / rect.height);
        return { x: (px - view.x) / view.zoom, y: (py - view.y) / view.zoom };
    }

    function cssFromWorld(wx, wy) {
        const rect = canvas.getBoundingClientRect();
        // Floating inputs are position:absolute children of <body>; go through
        // the canvas rect (robust to the canvas's offsetParent) to viewport
        // coords, then to document coords with scroll.
        const px = (wx * view.zoom + view.x) * (rect.width / canvas.width);
        const py = (wy * view.zoom + view.y) * (rect.height / canvas.height);
        return {
            left: rect.left + window.scrollX + px,
            top: rect.top + window.scrollY + py,
        };
    }

    // A map is ready to draw/navigate only while a floor is selected; Clear
    // Canvas leaves the last image loaded but blanks SelMapName, so this stops
    // a stray wheel/pan from resurrecting the cleared floor.
    function mapReady() {
        return img.naturalWidth > 0 && !!SelMapName;
    }

    // Synchronously drawable images. Icons drawn via fresh Image objects and
    // async onload callbacks ghosted the canvas during drags: pending loads
    // fired after newer frames had already cleared, stamping stale positions.
    const imageCache = new Map();
    function getCachedImage(url) {
        let cached = imageCache.get(url);
        if (!cached) {
            cached = new Image();
            cached.src = url;
            cached.onload = () => {
                if (mapReady() && !drawToolActive()) redrawAll();
            };
            imageCache.set(url, cached);
        }
        return cached.complete && cached.naturalWidth > 0 ? cached : null;
    }

    function redrawAll() {
        // While a zone/sub-zone is being drawn or edited, repaint through
        // drawZonePreview so the corner handles (and the shape-in-progress)
        // survive. Otherwise a tracking-poll redraw every tick would wipe the
        // handles mid-edit — they'd flash in on "Edit" and vanish on the next
        // poll. drawZonePreview repaints the elements too; the tracker overlay
        // then goes on top so the live fix still updates while editing.
        if (drawAreaButton.dataset.active === 'true' || drawSubZoneButton.dataset.active === 'true') {
            drawZonePreview();
            drawTrackOverlay();
            return;
        }
        clearCanvas();
        drawElements();
        drawTrackOverlay();
    }

    // ---- In-window dialogs (replace native alert/confirm) --------------------
    // A brief, non-blocking notice for informational messages.
    function bpsToast(message) {
        let host = document.getElementById("bpsToastHost");
        if (!host) {
            host = document.createElement("div");
            host.id = "bpsToastHost";
            host.className = "bps-toast-host";
            document.body.appendChild(host);
        }
        const el = document.createElement("div");
        el.className = "bps-toast";
        el.textContent = message;
        host.appendChild(el);
        setTimeout(() => { el.classList.add("bps-toast-out"); }, 3200);
        setTimeout(() => { el.remove(); }, 3600);
    }

    // A modal that resolves to true (confirm) or false (cancel). Replaces the
    // native confirm() so prompting stays inside the panel window.
    function bpsConfirm(message, opts = {}) {
        const { confirmText = "Confirm", cancelText = "Cancel", danger = false } = opts;
        return new Promise(resolve => {
            const overlay = document.createElement("div");
            overlay.className = "bps-modal-overlay";
            const dialog = document.createElement("div");
            dialog.className = "bps-modal";
            const msg = document.createElement("div");
            msg.className = "bps-modal-msg";
            msg.textContent = message;
            const row = document.createElement("div");
            row.className = "bps-modal-actions";
            const cancelBtn = document.createElement("button");
            cancelBtn.type = "button";
            cancelBtn.className = "bps-btn bps-btn-outline";
            cancelBtn.textContent = cancelText;
            const okBtn = document.createElement("button");
            okBtn.type = "button";
            okBtn.className = "bps-btn " + (danger ? "bps-btn-danger" : "bps-btn-primary");
            okBtn.textContent = confirmText;
            row.appendChild(cancelBtn);
            row.appendChild(okBtn);
            dialog.appendChild(msg);
            dialog.appendChild(row);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);
            const close = (val) => {
                overlay.remove();
                document.removeEventListener("keydown", onKey);
                resolve(val);
            };
            cancelBtn.addEventListener("click", () => close(false));
            okBtn.addEventListener("click", () => close(true));
            overlay.addEventListener("click", (e) => { if (e.target === overlay) close(false); });
            function onKey(e) {
                if (e.key === "Escape") close(false);
                else if (e.key === "Enter") close(true);
            }
            document.addEventListener("keydown", onKey);
            okBtn.focus();
        });
    }

    // A modal with one numeric input. Resolves to the entered number, to null
    // when the value is cleared (empty Save), or to undefined on cancel/Esc.
    // Used for the receiver mount height.
    function bpsPromptNumber(message, opts = {}) {
        const { initial = "", placeholder = "", min = 0, max = 10, confirmText = "Save" } = opts;
        return new Promise(resolve => {
            const overlay = document.createElement("div");
            overlay.className = "bps-modal-overlay";
            const dialog = document.createElement("div");
            dialog.className = "bps-modal";
            const msg = document.createElement("div");
            msg.className = "bps-modal-msg";
            msg.textContent = message;
            const input = document.createElement("input");
            input.type = "number";
            input.className = "bps-modal-input";
            input.step = "0.1";
            input.min = String(min);
            input.max = String(max);
            input.placeholder = placeholder;
            if (initial !== "" && Number.isFinite(initial)) input.value = String(initial);
            const row = document.createElement("div");
            row.className = "bps-modal-actions";
            const cancelBtn = document.createElement("button");
            cancelBtn.type = "button";
            cancelBtn.className = "bps-btn bps-btn-outline";
            cancelBtn.textContent = "Cancel";
            const okBtn = document.createElement("button");
            okBtn.type = "button";
            okBtn.className = "bps-btn bps-btn-primary";
            okBtn.textContent = confirmText;
            row.appendChild(cancelBtn);
            row.appendChild(okBtn);
            dialog.appendChild(msg);
            dialog.appendChild(input);
            dialog.appendChild(row);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);
            const openedAt = Date.now();
            const close = (val) => {
                overlay.remove();
                document.removeEventListener("keydown", onKey);
                resolve(val);
            };
            const commit = () => {
                // Unparsable content in a number input reads back as "" but
                // sets validity.badInput — it must fail validation, not be
                // mistaken for "cleared" and silently unset the stored value.
                if (input.validity.badInput) {
                    bpsToast(`Enter a number between ${min} and ${max}.`);
                    input.focus();
                    return;                                 // keep the modal open
                }
                const raw = input.value.trim();
                if (raw === "") { close(null); return; }   // cleared = unset
                const v = parseFloat(raw);
                if (!Number.isFinite(v) || v < min || v > max) {
                    bpsToast(`Enter a number between ${min} and ${max}.`);
                    input.focus();
                    return;                                 // keep the modal open
                }
                close(v);
            };
            cancelBtn.addEventListener("click", () => close(undefined));
            okBtn.addEventListener("click", commit);
            // Backdrop click cancels — but not within the opening instant: the
            // second click of a double-click on the launcher lands on the
            // overlay and would open-and-instantly-cancel the dialog.
            overlay.addEventListener("click", (e) => {
                if (e.target === overlay && Date.now() - openedAt > 300) close(undefined);
            });
            function onKey(e) {
                if (e.key === "Escape") close(undefined);
                // Enter on the focused Cancel button must cancel, not save.
                else if (e.key === "Enter") {
                    if (document.activeElement === cancelBtn) close(undefined);
                    else commit();
                }
            }
            document.addEventListener("keydown", onKey);
            input.focus();
        });
    }

    const createZoneId = () => `zone_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    let isDrawing = false;
    let SelMapName = "";
    let new_floor = true;
    let removefile = false;
    let imgfilename = "";
    // Multi-device tracking. `trackedDevices` holds the entity keys (no
    // "sensor." prefix) currently being tracked, in add order — that order is a
    // device's stable slot, which sets its base hue (see deviceBaseHue), so its
    // icon, distance circles, trace path, and legend swatch all share a colour.
    // `activeDevice` is the one the icon selector/upload target (the highlighted
    // legend row).
    let trackedDevices = [];
    let activeDevice = "";
    let myScaleVal = null;
    const DEFAULT_TRACKER_ICON = "/bps/person.svg";
    const GOLDEN_ANGLE = 137.508;

    function ensureTrackerIconsStore() {
        if (!finalcords.tracker_icons || typeof finalcords.tracker_icons !== "object") {
            finalcords.tracker_icons = {};
        }
    }

    // The icon URL a given tracked device should draw with (its saved choice,
    // else the default person glyph). Legacy bare filenames map to /bps/ paths.
    function trackerIconFor(entKey) {
        ensureTrackerIconsStore();
        const storedIcon = finalcords.tracker_icons[entKey];
        if (storedIcon === "person.svg") {
            return "/bps/person.svg";
        }
        if (storedIcon === "beacon.svg") {
            return "/bps/beacon.svg";
        }
        return storedIcon || DEFAULT_TRACKER_ICON;
    }

    function ensureIconOption(value, label = null) {
        if (!trackerIconSelector) {
            return;
        }
        if (!value) {
            return;
        }
        const existing = Array.from(trackerIconSelector.options).find(option => option.value === value);
        if (existing) {
            if (label) {
                existing.textContent = label;
            }
            return;
        }
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label || value;
        trackerIconSelector.appendChild(option);
    }

    async function loadTrackerIcons() {
        if (!trackerIconSelector) {
            return;
        }
        // Keep defaults available even if API call fails.
        ensureIconOption("/bps/person.svg", "Person (default)");
        ensureIconOption("/bps/beacon.svg", "Beacon");
        try {
            const response = await bpsFetch("/api/bps/tracker_icons");
            if (!response.ok) {
                return;
            }
            const icons = await response.json();
            icons.forEach(icon => {
                if (icon && icon.value) {
                    ensureIconOption(icon.value, icon.label || icon.value);
                }
            });
        } catch (error) {
            console.error("Failed loading tracker icons:", error);
        }
    }

    // =================================================================
    // Fetch existing maps
    // =================================================================

        // The dropdown lists image filenames, but users think in floor names.
        // Show the floor's set name (matched to the file by the name<->filename
        // convention), falling back to the filename without its extension.
        function mapOptionLabel(filename) {
            const base = removeExtension(filename);
            const floor = (finalcords.floor || []).find(f => sameFloorName(f.name, base));
            return floor && floor.name ? floor.name : base;
        }

        async function getSavedMaps(){
            const mapsResponse = await bpsFetch('/api/bps/maps');
            if (!mapsResponse.ok) {
                console.error('Failed to fetch maps:', mapsResponse.statusText);
                bpsToast('Could not load maps.');
                return false;
            }
        
            const maps = await mapsResponse.json();
            mapSelector.innerHTML = '<option value="">--Please choose an option--</option>';
            maps.forEach(map => {
                const option = document.createElement('option');
                option.value = map;
                option.textContent = mapOptionLabel(map);
                mapSelector.appendChild(option);
            });
            return true;
        }
        
    
        // Once the maps are loaded, call fetchBPSData
        await loadTrackerIcons();
        let tmpsaved = await getSavedMaps();
        if (tmpsaved){
            await fetchBPSData();
        }
        // Load the linking snapshot so the sidebar's "not reporting" heads-up and
        // the Debugging tab are populated on load (both re-check on Refresh / when
        // the Debugging tab is opened).
        loadScannerLinking();


        let stoptrackstat = false;
        let pollTrackActive = false; // interval-based tracking session running
        function startTrackfunc(){
            stoptrackstat = false;
            pollTrackActive = true;
            tracePointsByDevice.clear(); // each session traces from its own start
            lastTracks.clear();
            focusedDevice = null;
            starttrackbtn.style.display = "none";
            stoptrackbtn.style.display = "";
            if (circleControl) circleControl.style.display = ""; // reveal while tracking
            if (traceControl) traceControl.style.display = "";
            const interval = setInterval(async () => {
                if (stoptrackstat) {
                    clearInterval(interval);
                    pollTrackActive = false;
                    stoptrackstat = false;
                    lastTracks.clear();
                    focusedDevice = null;
                    starttrackbtn.style.display = trackedDevices.length ? "" : "none";
                    stoptrackbtn.style.display = "none";
                    if (circleControl) circleControl.style.display = "none"; // hide when not tracking
                    if (traceControl) traceControl.style.display = "none";
                    zonediv.style.display = "none";
                    if (img.naturalWidth > 0) redrawAll();
                    return;
                }
                let apiresponse = await fetchBPSCords();
                if (!Array.isArray(apiresponse) || apiresponse.length === 0) {
                    return;
                }
                // /api/bps/cords returns every tracked device; pick out each one
                // we're following and stash its latest fix keyed by entity. The
                // list is read fresh each tick, so adding/removing a device mid-
                // session takes effect on the next poll.
                let activeResult = null, activeSame = true;
                trackedDevices.forEach(entKey => {
                    const result = apiresponse.find(item => item.ent === entKey);
                    if (!result || !Array.isArray(result.cords) || result.cords.length < 2) return;
                    const x = result.cords[0], y = result.cords[1];
                    // Record every fix for the trace-path overlay, whether or not
                    // the toggle is on: the trace must show the whole session when
                    // switched on mid-session. Points are tagged with the fix's own
                    // floor because cords are in that floor's pixel space.
                    recordTracePoint(entKey, x, y, result.floor || null);
                    // A missing floor can't be judged off-floor, so treat it as the
                    // current one (no dim/badge/switch) rather than a false warning.
                    const sameFloor = !result.floor || sameFloorName(result.floor, SelMapName);
                    lastTracks.set(entKey, {
                        x, y,
                        circles: sameFloor ? result.radii : null,
                        offFloor: !sameFloor,
                        floor: result.floor,
                    });
                    if (entKey === activeDevice) { activeResult = result; activeSame = sameFloor; }
                });
                // The single zone bar follows the active (highlighted) device,
                // falling back to the first tracked device if none is active.
                if (!activeResult && trackedDevices.length) {
                    const firstKey = trackedDevices[0];
                    activeResult = apiresponse.find(item => item.ent === firstKey) || null;
                    if (activeResult) activeSame = !activeResult.floor || sameFloorName(activeResult.floor, SelMapName);
                }
                if (img.naturalWidth > 0) redrawAll();
                if (activeResult) {
                    zonediv.style.display = "";
                    document.getElementById("zonevalue").textContent = activeResult.zone || "unknown";
                    updateFloorReadout(activeResult.floor, activeSame);
                } else {
                    zonediv.style.display = "none";
                }
            }, 500); // Run every half second
        }

        function stoptrackfunc(){
            stoptrackstat = true;
        }

        starttrackbtn.addEventListener("click", function() {
            if (trackedDevices.length === 0) {
                bpsToast("Add at least one device to track!");
                return;
            }
            startTrackfunc();
        });
        stoptrackbtn.addEventListener("click", stoptrackfunc);

        // "Switch to <floor>" (shown in the zone bar when the tracked device is
        // on another floor): load that floor's map so its fix renders correctly.
        // Tracking keeps running; the next poll tick sees the new SelMapName and
        // draws the icon + circles on-floor and clears the off-floor readout.
        const switchFloorBtn = document.getElementById("switchFloorBtn");
        if (switchFloorBtn) {
            switchFloorBtn.addEventListener("click", async () => {
                const target = switchFloorBtn.dataset.target;
                if (!target) return;
                mapSelector.value = target;
                await selectExistingMap(target);
            });
        }


    // =================================================================
    // Triliterate functionality
    // =================================================================
    // Latest fix per tracked device, keyed by entity: {x, y, circles, offFloor,
    // floor}. Replaces the old single lastTrack so every device draws each frame.
    const lastTracks = new Map();

    // Base hue for a tracked device, from its slot in trackedDevices. Golden-
    // angle spacing keeps colours far apart, and everything for that device (its
    // icon tint, distance lines, trace path, legend swatch) derives from this one
    // value so they always agree.
    function deviceBaseHue(entKey) {
        const idx = trackedDevices.indexOf(entKey);
        return Math.round(((idx < 0 ? 0 : idx) * GOLDEN_ANGLE) % 360);
    }
    function deviceColor(entKey) {
        return `hsl(${deviceBaseHue(entKey)}, 85%, 50%)`;
    }

    // Clicking a tracker beacon (on the map or its Tracking-section row) isolates
    // it: only its lines + path + icon are drawn. null = show every tracked
    // device. Cleared when the device is no longer tracked or a session
    // starts/stops.
    let focusedDevice = null;

    // Icon world size. Fixed to the canvas normally; while tracking it is zoom-
    // compensated so icons don't balloon when you zoom in — but only 2/3 as
    // strongly as the pills (the pills fully cancel zoom by dividing by z, so
    // dividing by z^(2/3) shrinks icons 2/3 as fast, keeping them a bit larger).
    function mapIconSize() {
        const base = canvas.width * 0.04;
        return pollTrackActive ? base / Math.pow(view.zoom || 1, 2 / 3) : base;
    }

    function drawTrackOverlay() {
        if (!pollTrackActive || lastTracks.size === 0) return;
        // A focus on a device that's gone (removed/stale) reverts to showing all.
        if (focusedDevice && !lastTracks.has(focusedDevice)) focusedDevice = null;
        const iconSize = mapIconSize();
        const entries = [...lastTracks.entries()]
            .filter(([entKey]) => !focusedDevice || entKey === focusedDevice);
        // "Solo" = a single device on screen (only one tracked, or one isolated
        // by a beacon click). Lines are coloured per receiver when solo (each line
        // reads back to its receiver), per device when several share the map (so
        // you can tell the devices apart).
        const solo = entries.length <= 1;
        // Layered bottom-to-top so nothing important is buried: distance circles/
        // lines, then the receiver icons on top of them, then the distance values,
        // then trace paths, then the beacon icons + labels on top of everything.
        const labels = drawDistanceMarks(entries, solo);
        drawTrackedReceiversOnTop(iconSize);
        drawDistanceLabels(labels);
        entries.forEach(([entKey, t]) => {
            drawTracePath(tracePointsByDevice.get(entKey), deviceBaseHue(entKey));
        });
        entries.forEach(([entKey, t]) => {
            const baseHue = deviceBaseHue(entKey);
            const src = trackerIconFor(entKey);
            const raw = getCachedImage(src);
            const fade = t.offFloor ? 0.35 : 1; // off-floor fix isn't real here
            if (raw) {
                ctx.save();
                ctx.globalAlpha = fade;
                ctx.drawImage(raw, t.x - iconSize / 2, t.y - iconSize / 2, iconSize, iconSize);
                ctx.restore();
                // A light wash of the device's colour over the glyph (10%) tints
                // it for identification while leaving the icon itself readable.
                const tinted = tintedImage(raw, src, `hsl(${baseHue}, 85%, 45%)`, iconSize);
                if (tinted) {
                    ctx.save();
                    ctx.globalAlpha = fade * 0.1;
                    ctx.drawImage(tinted, t.x - iconSize / 2, t.y - iconSize / 2, iconSize, iconSize);
                    ctx.restore();
                }
            }
            // Name pill so each marker is identifiable on the map (colour matches
            // the legend); off-floor devices also get the red "on <floor>" pill.
            drawLabelPill(entKey, t.x, t.y + iconSize / 2 + 16, baseHue);
            if (t.offFloor && t.floor) {
                drawLabelPill(`on ${t.floor}`, t.x, t.y + iconSize / 2 + 44, 0);
            }
        });
    }

    // Hue keyed to the receiver's index on the floor (matched by placed
    // coordinates), so a receiver's icon and its distance line (in the single-
    // device view) share a color; golden-angle spacing keeps neighboring hues
    // contrasting.
    function floorReceiverHue(x, y) {
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const receivers = (floor && floor.receivers) || [];
        for (let i = 0; i < receivers.length; i++) {
            const c = receivers[i].cords;
            if (c && Math.abs(c.x - x) < 0.5 && Math.abs(c.y - y) < 0.5) {
                return Math.round((i * 137.508) % 360);
            }
        }
        return Math.abs(Math.round(x) * 31 + Math.round(y) * 17) % 360;
    }

    const beaconBase = new Image();
    beaconBase.src = "beacon.svg";
    const beaconTintCache = new Map();

    // Recolor the beacon glyph to `fill` (any CSS color) via source-in, cached
    // per (color, size). Returns null until the SVG has loaded.
    function tintedBeacon(fill, size) {
        if (!beaconBase.complete || beaconBase.naturalWidth === 0) return null;
        const px = Math.max(8, Math.round(size));
        const key = `${fill}|${px}`;
        let tile = beaconTintCache.get(key);
        if (!tile) {
            tile = document.createElement("canvas");
            tile.width = px;
            tile.height = px;
            const tctx = tile.getContext("2d");
            tctx.drawImage(beaconBase, 0, 0, px, px);
            tctx.globalCompositeOperation = "source-in";
            tctx.fillStyle = fill;
            tctx.fillRect(0, 0, px, px);
            beaconTintCache.set(key, tile);
        }
        return tile;
    }

    // Recolor an arbitrary already-loaded glyph (person/beacon/uploaded tracker
    // icon) to `fill` via source-in, cached per (src, color, size). Lets each
    // tracked device's marker take its own colour. Returns null if the image
    // isn't drawable yet.
    const iconTintCache = new Map();
    function tintedImage(img, srcKey, fill, size) {
        if (!img || !img.complete || img.naturalWidth === 0) return null;
        const px = Math.max(8, Math.round(size));
        const key = `${srcKey}|${fill}|${px}`;
        let tile = iconTintCache.get(key);
        if (!tile) {
            tile = document.createElement("canvas");
            tile.width = px;
            tile.height = px;
            const tctx = tile.getContext("2d");
            tctx.drawImage(img, 0, 0, px, px);
            tctx.globalCompositeOperation = "source-in";
            tctx.fillStyle = fill;
            tctx.fillRect(0, 0, px, px);
            iconTintCache.set(key, tile);
        }
        return tile;
    }

    const OFFLINE_RED = "#d32f2f";

    // Icon color: while tracking with distance lines enabled each receiver takes
    // its own hue (golden-angle by index) so receivers stay distinguishable. In
    // the single-device view the lines share this per-receiver hue, so a line
    // reads back to its receiver's icon; with several devices the lines are
    // per-device instead and this stays the receiver's own identity colour.
    // Otherwise an offline receiver is tinted red (matching its "(Offline)"
    // label) so a dead node stands out; otherwise the plain black glyph. The hue
    // tint is gated on an active tracking session because that is the only time
    // the distance-lines toggle is shown.
    function drawReceiverIcon(x, y, iconSize, offline) {
        let fill = null;
        if (circleToggle.checked && pollTrackActive) {
            fill = `hsl(${floorReceiverHue(x, y)}, 90%, 42%)`;
        } else if (offline) {
            fill = OFFLINE_RED;
        }
        if (fill) {
            const tinted = tintedBeacon(fill, iconSize);
            if (tinted) {
                ctx.drawImage(tinted, x - iconSize / 2, y - iconSize / 2, iconSize, iconSize);
                return;
            }
        }
        const base = getCachedImage("beacon.svg");
        if (base) {
            ctx.drawImage(base, x - iconSize / 2, y - iconSize / 2, iconSize, iconSize);
        }
    }

    // A rounded, filled pill with centered white text, clamped to the canvas
    // so it stays readable over whatever it covers. Sized in screen pixels
    // regardless of map zoom (every dimension divided by view.zoom, like the
    // grid labels): zooming in shrinks the pills relative to the map, so a dense
    // cluster of distances spreads out and stays legible as you zoom in.
    function drawLabelPill(text, cx, cy, hue, fillOverride) {
        const z = view.zoom || 1;
        ctx.font = `600 ${18 / z}px system-ui, sans-serif`;
        const padX = 8 / z;
        const height = 26 / z;
        const width = ctx.measureText(text).width + padX * 2;
        const x = Math.max(2, Math.min(canvas.width - width - 2, cx - width / 2));
        const y = Math.max(2, Math.min(canvas.height - height - 2, cy - height / 2));
        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(x, y, width, height, 8 / z);
        } else {
            ctx.rect(x, y, width, height);
        }
        ctx.fillStyle = fillOverride || `hsla(${hue}, 85%, 30%, 0.92)`;
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, x + padX, y + height - 8 / z);
        return { x, y, width, height };
    }

    // A zone's display colour: a manually-picked colour (zone.color) if set,
    // else a unique, stable auto colour (golden-angle by the zone's order among
    // the floor's zones). The map canvas and the sidebar header share this so
    // they always agree.
    function zoneDisplayColor(zone, index) {
        const c = zone && zone.color;
        if (typeof c === "string" && c) return c;
        return `hsl(${Math.round((index * 137.508) % 360)}, 68%, 60%)`;
    }
    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const k = n => (n + h / 30) % 12;
        const a = s * Math.min(l, 1 - l);
        const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
        const to = x => Math.round(255 * x).toString(16).padStart(2, "0");
        return `#${to(f(0))}${to(f(8))}${to(f(4))}`;
    }
    // Any zone colour we emit (hex or hsl) -> "#rrggbb" for <input type=color>.
    function colorToHex(color) {
        color = String(color || "");
        let m = /^#([0-9a-f]{6})$/i.exec(color);
        if (m) return "#" + m[1].toLowerCase();
        m = /^#([0-9a-f]{3})$/i.exec(color);
        if (m) return "#" + m[1].split("").map(c => c + c).join("").toLowerCase();
        m = /^hsl\(\s*([\d.]+)[,\s]+([\d.]+)%[,\s]+([\d.]+)%/i.exec(color);
        if (m) return hslToHex(+m[1], +m[2], +m[3]);
        return "#888888";
    }
    // Any zone colour -> a safe translucent rgba/hsla for a CSS overlay (only
    // recognised formats pass through, so a hand-edited colour can't inject CSS).
    function colorToTranslucent(color, alpha) {
        color = String(color || "");
        let m = /^#([0-9a-f]{6})$/i.exec(color);
        if (m) { const h = m[1]; return `rgba(${parseInt(h.slice(0,2),16)}, ${parseInt(h.slice(2,4),16)}, ${parseInt(h.slice(4,6),16)}, ${alpha})`; }
        m = /^#([0-9a-f]{3})$/i.exec(color);
        if (m) { const h = m[1]; return `rgba(${parseInt(h[0]+h[0],16)}, ${parseInt(h[1]+h[1],16)}, ${parseInt(h[2]+h[2],16)}, ${alpha})`; }
        m = /^hsl\(\s*([\d.]+)[,\s]+([\d.]+)%[,\s]+([\d.]+)%/i.exec(color);
        if (m) return `hsla(${m[1]}, ${m[2]}%, ${m[3]}%, ${alpha})`;
        return "";
    }
    // Hue (0-359) of a "#rrggbb", then of any zone colour (hex or hsl).
    function hexToHue(hex) {
        const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
        if (!m) return 0;
        const r = parseInt(m[1].slice(0, 2), 16) / 255, g = parseInt(m[1].slice(2, 4), 16) / 255, b = parseInt(m[1].slice(4, 6), 16) / 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
        if (d === 0) return 0;
        let h;
        if (max === r) h = ((g - b) / d) % 6;
        else if (max === g) h = (b - r) / d + 2;
        else h = (r - g) / d + 4;
        h = Math.round(h * 60);
        return (h + 360) % 360;
    }
    function colorToHue(color) { return hexToHue(colorToHex(color)); }

    // How a sub-zone is drawn. Sub-zones are ALWAYS coloured, and every sub-zone
    // within the same parent zone gets a DISTINCT colour. When the parent zone is
    // coloured, the siblings are different SHADES of the zone's own hue (same
    // hue, spread across lightness) so they read as belonging to the room while
    // staying distinct from each other; at double the baseline opacity.
    // Otherwise (parent uncoloured or orphaned) the siblings are spaced by the
    // golden angle at the light baseline opacity.
    function subZoneRenderColor(sub, floor) {
        const zones = (floor && floor.zones) || [];
        const subs = (floor && floor.subzones) || [];
        const pid = sub && sub.parent;
        const siblings = subs.filter(s => s && s.parent === pid);
        const n = siblings.length || 1;
        const si = Math.max(0, siblings.indexOf(sub));
        const pi = zones.findIndex(z => (z.zone_id || z.entity_id) === pid);
        if (pi >= 0 && !zones[pi].uncolored) {
            const hue = colorToHue(zoneDisplayColor(zones[pi], pi)); // the zone's own hue
            // Distinct shade per sibling: lightness fanned across 30%..62% (darker
            // + more saturated than the zone's faint tint, so each stands out).
            const light = n > 1 ? Math.round(30 + (si / (n - 1)) * 32) : 44;
            return { color: `hsl(${hue}, 80%, ${light}%)`, alpha: 0.44 };
        }
        const hue = Math.round((si * 137.508) % 360);
        return { color: `hsl(${hue}, 95%, 55%)`, alpha: 0.22 };
    }

    // A filled rounded pill with a name in an explicit colour, clamped to the
    // canvas. Used for zone/sub-zone name tags (pill = the shape's colour at
    // full opacity, text black).
    function drawColorPill(text, cx, cy, bgColor, textColor, fontPx) {
        if (!text) return;
        const fs = fontPx || 18;
        ctx.font = `700 ${fs}px system-ui, sans-serif`;
        const width = ctx.measureText(text).width + 20;
        const height = fs + 12;
        const x = Math.max(2, Math.min(canvas.width - width - 2, cx - width / 2));
        const y = Math.max(2, Math.min(canvas.height - height - 2, cy - height / 2));
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, width, height, height / 2);
        else ctx.rect(x, y, width, height);
        ctx.fillStyle = bgColor;
        ctx.fill();
        ctx.fillStyle = textColor;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, x + width / 2, y + height / 2 + 1);
        ctx.textAlign = "start";
        ctx.textBaseline = "alphabetic";
    }

    // Build a closed polygon path from points (caller then fills/strokes/clips).
    function tracePolygon(pts) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let p = 1; p < pts.length; p++) ctx.lineTo(pts[p].x, pts[p].y);
        ctx.closePath();
    }

    // Fill a polygon with grey diagonal hatching — the "no-go zone" look
    // (issue #60): dead space a tracker can't be in, distinct from a room's
    // flat colour tint. Lines are clipped to the polygon so they never bleed.
    function drawHatchedZone(pts) {
        const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
        const minx = Math.min(...xs), maxx = Math.max(...xs);
        const miny = Math.min(...ys), maxy = Math.max(...ys);
        ctx.save();
        tracePolygon(pts);
        ctx.clip();
        // Faint grey wash so the area still reads as filled at a glance.
        ctx.globalAlpha = 0.15;
        ctx.fillStyle = "#616161";
        ctx.fill();
        // Diagonal hatch lines across the bounding box (clip keeps them inside).
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = "#616161";
        ctx.lineWidth = 2;
        const step = 24;
        ctx.beginPath();
        for (let d = miny - (maxx - minx); d <= maxy; d += step) {
            ctx.moveTo(minx, d);
            ctx.lineTo(maxx, d + (maxx - minx));
        }
        ctx.stroke();
        ctx.restore();
    }

    // The radii filtered to finite, positive circles — and, when a receiver is
    // focused, just that receiver's. Shared by the circle (solo) and line (multi)
    // distance overlays.
    function validRadii(circles) {
        let focusCoords = null;
        if (focusedReceiver) {
            const focusFloor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const focused = focusFloor && (focusFloor.receivers || []).find(r => r.entity_id === focusedReceiver);
            if (focused && focused.cords) focusCoords = focused.cords;
        }
        return circles.filter(c =>
            Array.isArray(c) && [c[0], c[1], c[2]].every(Number.isFinite) && c[2] > 0
            && (!focusCoords || (Math.abs(c[0] - focusCoords.x) < 0.5 && Math.abs(c[1] - focusCoords.y) < 0.5)));
    }

    // The measured distance for radius `r` (pixels) as a display string in the
    // active grid unit, or null when the floor has no scale set.
    function distanceLabel(r) {
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const scale = floor && floor.scale;
        if (!scale) return null;
        const meters = r / scale;
        return gridUnit === "ft" ? `${(meters * 3.28084).toFixed(1)} ft` : `${meters.toFixed(1)} m`;
    }

    // Draw the distance circles/lines for every shown device and return the
    // per-receiver distance labels to draw later (so the receiver icons and then
    // the labels can be layered on top). Colour is per receiver when a single
    // device is shown (`solo` — each mark reads back to its receiver, matching
    // that receiver's icon) and per device otherwise (so the devices stay apart).
    //   Solo: the full trilateration picture — a thick line from the receiver to
    //   the tracker, then each receiver's measured distance as a circle (faint
    //   tint inside, receiver-coloured ring) drawn over the line so the ring's
    //   edge overlaps it.
    //   Multi: circles from several beacons pile into noise, so just a thin line
    //   from each beacon to the receivers hearing it.
    // Returns a Map: receiver coord key -> [{order, text, hue, x, y}].
    function drawDistanceMarks(entries, solo) {
        const labels = new Map();
        if (!circleToggle.checked) return labels;
        entries.forEach(([entKey, t]) => {
            if (!Array.isArray(t.circles)) return; // off-floor: no distance overlay
            const order = trackedDevices.indexOf(entKey);
            const valid = validRadii(t.circles);
            const hueOf = (c) => solo ? floorReceiverHue(c[0], c[1]) : deviceBaseHue(entKey);
            ctx.save();
            ctx.lineCap = "round";
            if (solo) {
                // Thick receiver -> tracker connectors first, so the circle rings
                // (next) overlap them at the edge.
                valid.forEach((c) => {
                    ctx.beginPath();
                    ctx.moveTo(t.x, t.y);
                    ctx.lineTo(c[0], c[1]);
                    ctx.strokeStyle = `hsla(${hueOf(c)}, 90%, 42%, 0.9)`;
                    ctx.lineWidth = 5;
                    ctx.stroke();
                });
                // Circles on top: faint tint inside, receiver-coloured ring.
                valid.forEach((c) => {
                    const hue = hueOf(c);
                    ctx.beginPath();
                    ctx.arc(c[0], c[1], c[2], 0, Math.PI * 2);
                    ctx.fillStyle = `hsla(${hue}, 95%, 55%, 0.10)`;
                    ctx.fill();
                    ctx.strokeStyle = `hsla(${hue}, 95%, 48%, 0.95)`;
                    ctx.lineWidth = 3;
                    ctx.stroke();
                });
            } else {
                valid.forEach((c) => {
                    ctx.beginPath();
                    ctx.moveTo(t.x, t.y);
                    ctx.lineTo(c[0], c[1]);
                    ctx.strokeStyle = `hsla(${hueOf(c)}, 90%, 50%, 0.55)`;
                    ctx.lineWidth = 2.5;
                    ctx.stroke();
                });
            }
            ctx.restore();
            valid.forEach((c) => {
                const text = distanceLabel(c[2]);
                if (!text) return;
                const key = `${Math.round(c[0])},${Math.round(c[1])}`;
                let arr = labels.get(key);
                if (!arr) { arr = []; labels.set(key, arr); }
                arr.push({ order, text, hue: hueOf(c), x: c[0], y: c[1] });
            });
        });
        return labels;
    }

    // Redraw the current floor's receiver icons so they sit on top of the
    // distance circles/lines (which were painted over the base render). Mirrors
    // drawElements' guards so a hidden/focused receiver behaves the same.
    function drawTrackedReceiversOnTop(iconSize) {
        if (!circleToggle.checked || receiversHidden()) return; // nothing drawn over them otherwise
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        if (!floor) return;
        (floor.receivers || []).forEach(r => {
            if (!r.cords) return;
            if (focusedReceiver && r.entity_id !== focusedReceiver) return;
            drawReceiverIcon(r.cords.x, r.cords.y, iconSize, isReceiverOffline(r.entity_id));
        });
    }

    // Draw each receiver's distance values, positioned by how many it has (a
    // receiver heard by several tracked beacons gets one pill per beacon):
    //   1-3 -> a vertical stack centred on the receiver;
    //   4   -> a 2x2 grid around it;
    //   5+  -> evenly spaced around it (pentagon at 5, hexagon at 6, ...).
    // Pills are ordered by the device's slot in the Tracking section (top / first
    // position = first tracked). Called after the receiver icons so values stay
    // readable on top.
    function drawDistanceLabels(labels) {
        // Offsets are in pill-sized units divided by view.zoom, so the cluster
        // stays the same tight on-screen size as the pills at any zoom. Every
        // arrangement is centred on (rx, ry) = the receiver.
        const z = view.zoom || 1;
        const STEP = 28 / z; // pill height (26) plus a hair of gap
        labels.forEach((arr) => {
            arr.sort((a, b) => a.order - b.order);
            const n = arr.length;
            const rx = arr[0].x, ry = arr[0].y;
            const place = (lab, cx, cy) => drawLabelPill(lab.text, cx, cy, lab.hue);
            if (n <= 3) {
                arr.forEach((lab, j) => place(lab, rx, ry + (j - (n - 1) / 2) * STEP));
            } else if (n === 4) {
                const dx = 34 / z, dy = STEP / 2;
                const offs = [[-dx, -dy], [dx, -dy], [-dx, dy], [dx, dy]]; // TL, TR, BL, BR
                arr.forEach((lab, j) => place(lab, rx + offs[j][0], ry + offs[j][1]));
            } else {
                // Snug ring, growing just enough with count to stay centred;
                // spaced a touch wider (25%) so 5+ pills stay legible.
                const R = 1.25 * Math.max(STEP, (n * 6) / z);
                arr.forEach((lab, j) => {
                    const ang = -Math.PI / 2 + (j / n) * Math.PI * 2; // first at top, clockwise
                    const c = Math.cos(ang), s = Math.sin(ang);
                    // Push the low pills (e.g. the pentagon's bottom pair) apart
                    // horizontally so they don't crowd together under the receiver.
                    const xSpread = s > 0.3 ? 1.45 : 1;
                    place(lab, rx + R * c * xSpread, ry + R * s);
                });
            }
        });
    }

    // =================================================================
    // Receiver-to-receiver distance overlay (Tracking column toggle)
    // =================================================================

    // The drawable receiver-to-receiver links for the floor on screen, from the
    // latest calibration solve: directional matrix rows merged per sorted pair,
    // kept only when both endpoints are placed here right now. Shared by the
    // overlay painter, the hit-tester (the neighbour icons the overlay draws
    // must be hittable), and the toggle's feedback toast — all three must agree
    // on what is on screen. Returns ALL links (no focus filter; consumers apply
    // it) plus whether a solve exists at all, so the toast can tell "no data"
    // from "data no longer matches the placed receivers".
    function receiverDistanceLinks() {
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        // The toggle lives in the Tracking column, which drawElements hides for
        // floors with fewer than three receivers — never paint an overlay whose
        // off-switch isn't reachable.
        if (!floor || (floor.receivers || []).length < 3) return { links: [], result: null };
        const result = selectedFloorResult(calibLastResults, SelMapName);
        const matrix = (result && result.matrix) || [];
        const bySlug = new Map((floor.receivers || [])
            .filter(r => r && r.cords && Number.isFinite(r.cords.x) && Number.isFinite(r.cords.y))
            .map(r => [r.entity_id, r.cords]));
        // Mount heights (m), for the live 3D truth below. null = not set.
        const heightBySlug = new Map((floor.receivers || [])
            .filter(r => r && r.entity_id)
            .map(r => [r.entity_id, Number.isFinite(r.height) ? r.height : null]));
        // Which detected distance the pill shows and the colour is judged on:
        // "calibrated" = the measured distance after the per-receiver correction
        // (residual error after calibration); "raw" = the uncorrected reading
        // (the sensor's own error). Both keep the real map distance as the
        // reference, so flipping the mode shows exactly what calibration did.
        const rawMode = recDistMode.value === "raw";
        const clampP = (v) => Math.max(-1, Math.min(1, v));
        const byPair = new Map(); // "a|b" (sorted) -> {a, b, cal:[...], raw:[...], psCal:[...], psRaw:[...], true_m}
        matrix.forEach(m => {
            if (!bySlug.has(m.tx) || !bySlug.has(m.rx)) return;
            if (!Number.isFinite(m.corrected_m) || !Number.isFinite(m.measured_m)
                || !Number.isFinite(m.true_m) || m.true_m <= 0) return;
            const [a, b] = [m.tx, m.rx].sort();
            let link = byPair.get(`${a}|${b}`);
            if (!link) { link = { a, b, cal: [], raw: [], psCal: [], psRaw: [], true_m: m.true_m }; byPair.set(`${a}|${b}`, link); }
            link.cal.push(m.corrected_m);
            link.raw.push(m.measured_m);
            // Per-direction error, kept separately: the rx-side correction is
            // baked into corrected_m but the tx-side bias is not, so the two
            // directions genuinely differ — colour must reflect the worse one,
            // or a one-sided anomaly averages toward green.
            link.psCal.push(clampP(m.corrected_m / m.true_m - 1));
            link.psRaw.push(clampP(m.measured_m / m.true_m - 1));
        });
        const avg = (arr) => arr.reduce((s, v) => s + v, 0) / arr.length;
        const worst = (arr) => arr.reduce((w, p) => Math.abs(p) > Math.abs(w) ? p : w, 0);
        let links = [];
        byPair.forEach(link => {
            const A = bySlug.get(link.a), B = bySlug.get(link.b);
            // The detected distance + its worst-direction error for the chosen
            // mode; the pill and colour both use these, so number and colour agree.
            const detected = rawMode ? avg(link.raw) : avg(link.cal);
            const worstP = rawMode ? worst(link.psRaw) : worst(link.psCal);
            // true_m was computed from the positions at SOLVE time. If an
            // endpoint has been moved since (compare against the live map
            // distance), the whole row is stale: judging the new geometry with
            // the old numbers would flag a placement change as a calibration
            // error. Such links are drawn neutral until the next solve.
            // Mount heights make the live truth 3D, matching the backend's
            // true_m — so setting or changing a height after a solve flags the
            // link stale (grey, "recalibrate") exactly like moving it would.
            let liveM = floor.scale
                ? Math.hypot(A.x - B.x, A.y - B.y) / floor.scale : null;
            const hA = heightBySlug.get(link.a), hB = heightBySlug.get(link.b);
            if (liveM !== null && Number.isFinite(hA) && Number.isFinite(hB)) {
                liveM = Math.hypot(liveM, hA - hB);
            }
            const stale = liveM !== null
                && Math.abs(liveM - link.true_m) > Math.max(0.1, 0.02 * link.true_m);
            // Colour, and the filter category taken FROM that same hue so the
            // filter matches the colour actually on the map (and in the
            // calibration table, which shares this ramp): the green band is the
            // perceptually-green hue range ~90–150 (about ±25% error), warmer
            // than that reads red (measures long), cooler reads blue (measures
            // short). A stale link is grey — it carries no calibration colour.
            const hue = 240 - (worstP + 1) * 120;
            const cat = stale ? "stale" : hue < 90 ? "red" : hue > 150 ? "blue" : "green";
            links.push({
                a: link.a, b: link.b, A, B, detected, cat,
                trueM: link.true_m, liveM, stale, hue,
            });
        });
        // How many links the floor's calibration actually yields, before the
        // display filters below — lets the toast tell "no data" / "data no
        // longer matches the receivers" from "no links of the chosen colour".
        const matchedCount = links.length;
        // Colour filter: keep only links of the selected calibration colour
        // ("offcolour" = red or blue, i.e. every inaccurate link). Applied
        // before the closest-links limit so, e.g., "red + closest 2" means the
        // two nearest RED links, not the reds among the two nearest of any
        // colour. Stale (grey) links have no colour, so any filter hides them.
        const colorSel = recDistColor.value;
        if (colorSel !== "all") {
            links = links.filter(l => !l.stale && (
                colorSel === "offcolour" ? (l.cat === "red" || l.cat === "blue") : l.cat === colorSel));
        }
        // Closest-links limit: keep a link only when one of its endpoints
        // counts the other among its K nearest neighbours (by current map
        // distance), so each receiver contributes its K shortest lines and no
        // receiver is orphaned by a stricter mutual-K rule. 0 = no limit.
        const k = Number(recDistCount.value) || 0;
        if (k > 0) {
            const byReceiver = new Map();
            links.forEach(l => {
                [l.a, l.b].forEach(id => {
                    if (!byReceiver.has(id)) byReceiver.set(id, []);
                    byReceiver.get(id).push(l);
                });
            });
            const keep = new Set();
            byReceiver.forEach(arr => {
                arr.sort((x, y) =>
                    (x.liveM !== null ? x.liveM : x.trueM) - (y.liveM !== null ? y.liveM : y.trueM));
                arr.slice(0, k).forEach(l => keep.add(l));
            });
            links = links.filter(l => keep.has(l));
        }
        return { links, result, matchedCount };
    }

    // Every pair of receivers that measure each other, as a line with a pill at
    // its middle: "measured-after-correction (real map distance)". The data is
    // the latest calibration solve for this floor. Line and pill take the
    // calibration table's error colour (blue = measures short, green =
    // accurate, red = long) so a bad receiver stands out at a glance; a link
    // whose endpoint moved since the solve is grey and dashed instead, showing
    // the live map distance without passing a stale judgement. When a receiver
    // is focused (map or sidebar click) only its links are shown — its
    // immediate neighbours' icons are then drawn here, since drawElements hides
    // every other receiver while one is focused, and a line needs both
    // endpoints visible. Called at the end of drawElements so the lines sit on
    // top of the base render (tracking overlays still paint above).
    // The links currently on screen. A single-link highlight (clicked line or
    // pill) wins over a focused receiver, which wins over "show all"; a
    // highlight whose link no longer exists (closest-count changed, a receiver
    // moved out) is reconciled back to "show all". Shared by the painter and
    // the line/pill hit-test so a link is clickable exactly where it is drawn.
    function shownRecDistLinks() {
        if (!recDistToggle.checked || receiversHidden()) return [];
        const all = receiverDistanceLinks().links;
        if (focusedRecDistLink && !all.some(l => `${l.a}|${l.b}` === focusedRecDistLink)) {
            focusedRecDistLink = null;
        }
        if (focusedRecDistLink) return all.filter(l => `${l.a}|${l.b}` === focusedRecDistLink);
        if (focusedReceiver) return all.filter(l => l.a === focusedReceiver || l.b === focusedReceiver);
        return all;
    }

    const RECDIST_STALE = "hsla(0, 0%, 42%, 0.92)";
    function drawReceiverDistances() {
        recDistDrawn = [];
        // The colour legend tracks the overlay exactly: hidden unless we draw at
        // least one link below (so it's gone when the toggle is off, no floor,
        // off-floor, or the data doesn't match the placed receivers).
        if (recDistLegend) recDistLegend.style.display = "none";
        if (!recDistToggle.checked || receiversHidden()) return;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const links = shownRecDistLinks();
        if (!links.length) return;
        if (recDistLegend) recDistLegend.style.display = "";
        const fmt = (meters) => gridUnit === "ft"
            ? `${(meters * 3.28084).toFixed(1)} ft` : `${meters.toFixed(1)} m`;
        // While actively hovering a line or a receiver, the link(s) being
        // inspected stay full strength and every other line dims to 10% so the
        // hovered path stands out of a dense mesh. A hovered receiver lights up
        // all of its links; a hovered line just itself. No hover -> no dimming.
        const hoverKeys = hoveredRecDistLink
            ? new Set([hoveredRecDistLink])
            : hoveredReceiver
                ? new Set(links.filter(l => l.a === hoveredReceiver || l.b === hoveredReceiver)
                    .map(l => `${l.a}|${l.b}`))
                : null;
        const dimming = !!(hoverKeys && hoverKeys.size);
        ctx.save();
        ctx.lineCap = "round";
        links.forEach(l => {
            const key = `${l.a}|${l.b}`;
            const highlighted = focusedRecDistLink === key;
            const active = !dimming || hoverKeys.has(key);
            const alpha = active ? (l.stale ? 0.8 : 0.85) : 0.1;
            // A white casing under a highlighted line lifts it off the map art.
            if (highlighted) {
                ctx.beginPath();
                ctx.moveTo(l.A.x, l.A.y);
                ctx.lineTo(l.B.x, l.B.y);
                ctx.setLineDash([]);
                ctx.strokeStyle = `rgba(255, 255, 255, ${active ? 0.9 : 0.1})`;
                ctx.lineWidth = 11;
                ctx.stroke();
            }
            ctx.beginPath();
            ctx.moveTo(l.A.x, l.A.y);
            ctx.lineTo(l.B.x, l.B.y);
            ctx.setLineDash(l.stale ? [10, 10] : []);
            ctx.strokeStyle = l.stale ? `hsla(0, 0%, 45%, ${alpha})` : `hsla(${l.hue}, 80%, 45%, ${alpha})`;
            ctx.lineWidth = highlighted ? 7 : 4;
            ctx.stroke();
        });
        ctx.restore();
        // Icons above the lines, for every line endpoint (this is what brings a
        // focused receiver's neighbours back on screen). Endpoint names follow
        // the same hover rule as drawElements, which skips non-focused
        // receivers entirely while one is focused.
        const endpoints = new Set();
        links.forEach(l => { endpoints.add(l.a); endpoints.add(l.b); });
        const iconSize = mapIconSize();
        ((floor && floor.receivers) || []).forEach(r => {
            if (!r.cords || !endpoints.has(r.entity_id)) return;
            const recOffline = isReceiverOffline(r.entity_id);
            drawReceiverIcon(r.cords.x, r.cords.y, iconSize, recOffline);
            if (r.entity_id === hoveredReceiver && r.entity_id !== focusedReceiver) {
                let labelY = r.cords.y - iconSize / 2 - 8;
                if (labelY < 24) labelY = r.cords.y + iconSize / 2 + 24;
                drawCenteredLabel((recOffline ? "(Offline) " : "") + r.entity_id, r.cords.x, labelY,
                    "600 22px system-ui, sans-serif", recOffline ? OFFLINE_RED : "#111111");
            }
        });
        // Pills are details-on-demand: on a dense floor the full set of labels
        // is unreadable, so a link shows its distance pill only when it's the
        // one being inspected — hovered (line or either endpoint), isolated
        // (focusedRecDistLink), or belonging to a focused receiver. The lines
        // themselves always carry the colour, which is the at-a-glance signal.
        // Pills last so the values stay readable over lines and icons; stale
        // links show the LIVE map distance in a neutral grey pill. Each line is
        // recorded for the hit-test, with its pill rect only when one was drawn.
        const focusedReceiverPills = !!focusedReceiver;
        links.forEach(l => {
            const key = `${l.a}|${l.b}`;
            const showPill = focusedReceiverPills
                || key === focusedRecDistLink
                || key === hoveredRecDistLink
                || (hoveredReceiver && (l.a === hoveredReceiver || l.b === hoveredReceiver));
            let pill = null;
            if (showPill) {
                const mx = (l.A.x + l.B.x) / 2, my = (l.A.y + l.B.y) / 2;
                pill = l.stale
                    ? drawLabelPill(`${fmt(l.detected)} (${fmt(l.liveM)}) — recalibrate`, mx, my, 0, RECDIST_STALE)
                    : drawLabelPill(`${fmt(l.detected)} (${fmt(l.trueM)})`, mx, my, l.hue);
            }
            recDistDrawn.push({ key, A: l.A, B: l.B, pill });
        });
    }

    // Distance from point p to segment a-b (world pixels).
    function distToSegment(p, a, b) {
        const vx = b.x - a.x, vy = b.y - a.y;
        const len2 = vx * vx + vy * vy;
        let t = len2 ? ((p.x - a.x) * vx + (p.y - a.y) * vy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        return Math.hypot(a.x + t * vx - p.x, a.y + t * vy - p.y);
    }

    // The receiver-distance link ("a|b") under the cursor, or null. Tests the
    // exact rects drawReceiverDistances recorded, so a link is hittable exactly
    // where it is drawn: pills first (they paint on top), then the nearest line
    // within a small slack.
    function hitRecDistLinkAt(pos) {
        if (!recDistToggle.checked || receiversHidden()) return null;
        for (let i = recDistDrawn.length - 1; i >= 0; i--) {
            const d = recDistDrawn[i];
            if (d.pill && pos.x >= d.pill.x && pos.x <= d.pill.x + d.pill.width
                && pos.y >= d.pill.y && pos.y <= d.pill.y + d.pill.height) return d.key;
        }
        let best = null, bestDist = canvas.width * 0.008 + 6; // ~22 world px slack
        recDistDrawn.forEach(d => {
            const dist = distToSegment(pos, d.A, d.B);
            if (dist <= bestDist) { bestDist = dist; best = d.key; }
        });
        return best;
    }

    // =================================================================
    // Trace path (the route taken during the active tracking session)
    // =================================================================

    // Fixes recorded since the session started, per tracked device, each in its
    // own floor's pixel space: entKey -> [{x, y, floor}, ...]. Recorded
    // regardless of the toggle so switching it on mid-session shows the whole
    // path; cleared when a session starts.
    const tracePointsByDevice = new Map();
    const TRACE_MAX_POINTS = 5000; // oldest dropped beyond this, per device

    function recordTracePoint(entKey, x, y, floor) {
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        let pts = tracePointsByDevice.get(entKey);
        if (!pts) { pts = []; tracePointsByDevice.set(entKey, pts); }
        const last = pts[pts.length - 1];
        // Skip sub-pixel moves so an idle device doesn't burn the point budget.
        if (last && last.floor === floor && Math.hypot(x - last.x, y - last.y) < 1) return;
        pts.push({ x, y, floor });
        if (pts.length > TRACE_MAX_POINTS) pts.shift();
    }

    // The polyline through one device's fixes, faded by recency (newest
    // brightest) so the direction of travel is readable, drawn in that device's
    // colour (`baseHue`). Only fixes belonging to the floor on screen are drawn
    // — an off-floor stretch breaks the line rather than connecting two
    // coordinates from different pixel spaces (a missing floor is treated as the
    // current one, like the tracking loop does). `points` is the device's trace
    // array; drawTrackOverlay calls this per tracked device.
    function drawTracePath(points, baseHue) {
        if (!traceToggle.checked || !Array.isArray(points) || points.length === 0) return;
        const tracePoints = points;
        const onFloor = (p) => !p.floor || sameFloorName(p.floor, SelMapName);
        // Segments between consecutive fixes with both ends on this floor.
        const segs = [];
        for (let i = 1; i < tracePoints.length; i++) {
            const a = tracePoints[i - 1], b = tracePoints[i];
            if (onFloor(a) && onFloor(b)) segs.push([a, b, i]);
        }
        ctx.save();
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        if (segs.length) {
            // Casing pass: one dark stroke under the whole path so the colored
            // line stays readable over map art, circle fills, and labels.
            // moveTo only where the previous segment isn't adjacent, so joints
            // stay inside one subpath and don't double-composite into beads.
            ctx.beginPath();
            let prev = -2;
            segs.forEach(([a, b, i]) => {
                if (i !== prev + 1) ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                prev = i;
            });
            ctx.strokeStyle = "rgba(15, 15, 20, 0.55)";
            ctx.lineWidth = 7;
            ctx.stroke();
            // Colored pass in a few recency buckets: one stroke per alpha level
            // instead of per segment, so long traces stay cheap to repaint.
            const BUCKETS = 8;
            const denom = Math.max(tracePoints.length - 1, 1);
            const bucketOf = (i) => Math.min(BUCKETS - 1, Math.floor(((i - 1) / denom) * BUCKETS));
            for (let bkt = 0; bkt < BUCKETS; bkt++) {
                ctx.beginPath();
                let any = false;
                prev = -2;
                segs.forEach(([a, b, i]) => {
                    if (bucketOf(i) !== bkt) return;
                    if (i !== prev + 1) ctx.moveTo(a.x, a.y);
                    ctx.lineTo(b.x, b.y);
                    prev = i;
                    any = true;
                });
                if (any) {
                    ctx.strokeStyle = `hsla(${baseHue}, 95%, 60%, ${(0.25 + 0.7 * ((bkt + 1) / BUCKETS)).toFixed(3)})`;
                    ctx.lineWidth = 3.5;
                    ctx.stroke();
                }
            }
        }
        // Session-start marker so the path's origin is readable.
        const first = tracePoints[0];
        if (onFloor(first)) {
            ctx.beginPath();
            ctx.arc(first.x, first.y, 7, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(15, 15, 20, 0.55)";
            ctx.fill();
            ctx.beginPath();
            ctx.arc(first.x, first.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = `hsl(${baseHue}, 95%, 60%)`;
            ctx.fill();
        }
        ctx.restore();
    }

    // Zone-bar floor readout for the tracked device. Muted "· <floor>" when it's
    // the floor on screen; a red "· on <floor> — not this floor" plus a
    // "Switch to <floor>" button (if that floor has a map) when it isn't.
    function updateFloorReadout(floorName, sameFloor) {
        const zf = document.getElementById("zonefloor");
        const btn = document.getElementById("switchFloorBtn");
        if (!zf) return;
        if (sameFloor || !floorName) {
            zf.textContent = floorName ? `· ${floorName}` : "";
            zf.classList.remove("bps-offfloor");
            if (btn) { btn.style.display = "none"; btn.dataset.target = ""; }
            return;
        }
        zf.textContent = `· on ${floorName} — not this floor`;
        zf.classList.add("bps-offfloor");
        // Offer to jump there, but only if a saved map matches that floor name.
        const opt = mapSelector && [...mapSelector.options]
            .find(o => o.value && sameFloorName(removeExtension(o.value), floorName));
        if (btn && opt) {
            btn.textContent = `Switch to ${floorName}`;
            btn.dataset.target = opt.value;
            btn.style.display = "";
        } else if (btn) {
            btn.style.display = "none";
            btn.dataset.target = "";
        }
    }

    // =================================================================
    // Other functions
    // =================================================================
        // Data saved before floor names were compared normalized can contain
        // floors differing only in case (e.g. "Main" and "MAIN"). All lookups
        // take the first match, so fold such duplicates into one entry.
        function mergeDuplicateFloors() {
            if (!Array.isArray(finalcords.floor)) return;
            const merged = [];
            finalcords.floor.forEach(floor => {
                const existing = merged.find(f => sameFloorName(f.name, floor.name));
                if (!existing) {
                    merged.push(floor);
                    return;
                }
                existing.receivers = existing.receivers || [];
                (floor.receivers || []).forEach(receiver => {
                    if (!existing.receivers.some(r => r.entity_id === receiver.entity_id)) {
                        existing.receivers.push(receiver);
                    }
                });
                existing.zones = (existing.zones || []).concat(floor.zones || []);
                existing.subzones = (existing.subzones || []).concat(floor.subzones || []);
                if (existing.scale == null) {
                    existing.scale = floor.scale;
                }
            });
            finalcords.floor = merged;
        }

        // Function to fetch data from the API and display it on page
        async function fetchBPSData() {
            const apiUrl = "/api/bps/read_text"; // API endpoint to read the file
        
            try {
                const response = await bpsFetch(apiUrl); // Make a GET request to the API
        
            if (!response.ok) {
                console.error("Failed to fetch BPS data:", response.statusText); // Handle error status
                return;
            }
        
            const data = await response.json();

            // Read the receiver list before parsing the coordinates: on a
            // fresh install bpsdata.txt is empty and JSON.parse would throw,
            // yet the receiver picker is needed exactly then.
            receiverOptions = Array.isArray(data.receivers) ? [...data.receivers].sort() : [];
            offlineReceivers = Array.isArray(data.offline_receivers) ? data.offline_receivers : [];
            scannerDiagnostics = (data.scanner_diagnostics && typeof data.scanner_diagnostics === 'object')
                ? data.scanner_diagnostics : { unmatched_receivers: [], unplaced_scanners: [] };
            console.log("Known receivers:", receiverOptions);

            if (data.coordinates) {
                finalcords = JSON.parse(data.coordinates);
                mergeDuplicateFloors();
                tmpfinalcords = finalcords; //Store original cords in a temp to compare later if it is changed
            }
            ensureTrackerIconsStore();
            // finalcords is now loaded; re-label the map dropdown (built earlier
            // at startup from filenames) with each floor's set name.
            Array.from(mapSelector.options).forEach(o => {
                if (o.value) o.textContent = mapOptionLabel(o.value);
            });
            console.log("Coordinates loaded:", finalcords);
            let ents = data.entities;
            console.log("Entities to track:", ents);

            entSelector.innerHTML = '<option value="">--Please choose an option--</option>';
            ents.forEach(ent => {
                const option = document.createElement('option');
                option.value = ent;
                option.textContent = ent;
                entSelector.appendChild(option);
            });

            } catch (error) {
                console.error("Error fetching BPS data:", error); // Handle possible error during fetch-call
            }
        }

        async function fetchBPSCords() {
            const apiUrl = "/api/bps/cords"; 
        
            try {
                const response = await bpsFetch(apiUrl); // Make a GET request to the API
        
            if (!response.ok) {
                console.error("Failed to fetch BPS data:", response.statusText); // Handle error status
                return [];
            }
        
            const data = await response.json();
            return data;

            } catch (error) {
            // Handle possible error during fetch-call
            console.error("Error fetching BPS data:", error);
            return [];
            }
        }

        // Make a device the active one: the icon selector/upload target it, and
        // its legend row is highlighted. Reflects its saved icon in the selector.
        function setActiveDevice(entKey) {
            activeDevice = entKey || "";
            if (trackerIconSelector && activeDevice) {
                const icon = trackerIconFor(activeDevice);
                ensureIconOption(icon);
                trackerIconSelector.value = icon;
            }
        }

        // Start/stop button visibility follows whether anything is tracked (but
        // Stop wins while a session is live — that's handled in the poll loop).
        function refreshTrackButtons() {
            if (pollTrackActive) return;
            starttrackbtn.style.display = trackedDevices.length ? "" : "none";
            stoptrackbtn.style.display = "none";
        }

        // The colour-coded list of tracked devices: swatch + name + remove button.
        // Clicking a row isolates that device on the map (hides the others) and
        // makes it the active device for the icon controls; clicking the isolated
        // row again reverts to showing all. Rebuilt whenever the set, active, or
        // focused device changes; swatch colours match each device's on-map colour.
        function renderTrackLegend() {
            const legend = document.getElementById("trackLegend");
            if (!legend) return;
            legend.innerHTML = "";
            if (trackedDevices.length === 0) {
                legend.style.display = "none";
                return;
            }
            legend.style.display = "";
            trackedDevices.forEach(entKey => {
                const row = document.createElement("div");
                row.className = "bps-track-legend-row"
                    + (entKey === activeDevice ? " is-active" : "")
                    + (entKey === focusedDevice ? " is-focused" : "");
                const swatch = document.createElement("span");
                swatch.className = "bps-track-swatch";
                swatch.style.background = deviceColor(entKey);
                const name = document.createElement("span");
                name.className = "bps-track-name";
                name.textContent = entKey;
                name.title = "Click to isolate this device on the map (click again to show all)";
                // Isolate on the map (toggle), and target the icon controls at it.
                const pick = () => {
                    setActiveDevice(entKey);
                    focusedDevice = focusedDevice === entKey ? null : entKey;
                    renderTrackLegend();
                    if (pollTrackActive && img.naturalWidth > 0) redrawAll();
                };
                swatch.addEventListener("click", pick);
                name.addEventListener("click", pick);
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "bps-track-remove";
                remove.textContent = "×";
                remove.title = "Stop tracking this device";
                remove.addEventListener("click", () => removeTrackedDevice(entKey));
                row.appendChild(swatch);
                row.appendChild(name);
                row.appendChild(remove);
                legend.appendChild(row);
            });
        }

        function addTrackedDevice(entKey) {
            if (!entKey) return;
            if (!trackedDevices.includes(entKey)) trackedDevices.push(entKey);
            setActiveDevice(entKey);
            renderTrackLegend();
            refreshTrackButtons();
        }

        function removeTrackedDevice(entKey) {
            trackedDevices = trackedDevices.filter(d => d !== entKey);
            lastTracks.delete(entKey);
            tracePointsByDevice.delete(entKey);
            if (focusedDevice === entKey) focusedDevice = null;
            if (activeDevice === entKey) setActiveDevice(trackedDevices[0] || "");
            renderTrackLegend();
            if (trackedDevices.length === 0 && pollTrackActive) stoptrackfunc();
            refreshTrackButtons();
            if (pollTrackActive && img.naturalWidth > 0) redrawAll();
        }

        // Choose a device to add to the tracked set. The dropdown resets after
        // each pick so the same device can be re-added once removed.
        entSelector.addEventListener('change', async () => {
            const val = entSelector.value;
            if (!val) return;
            addTrackedDevice(val);
            entSelector.value = "";
        });

        if (trackerIconSelector) {
            trackerIconSelector.addEventListener("change", () => {
                if (!activeDevice) {
                    return;
                }
                ensureTrackerIconsStore();
                finalcords.tracker_icons[activeDevice] = trackerIconSelector.value;
                savebuttondiv.appendChild(saveButton);
                if (pollTrackActive && img.naturalWidth > 0) redrawAll();
            });
        }

        if (uploadTrackerIconButton && trackerIconUpload) {
            uploadTrackerIconButton.addEventListener("click", async () => {
                if (!activeDevice) {
                    bpsToast("Add a device to track first.");
                    return;
                }
                const iconFile = trackerIconUpload.files[0];
                if (!iconFile) {
                    bpsToast("Choose an icon file first.");
                    return;
                }
                const uploadData = new FormData();
                uploadData.append("icon", iconFile);
                try {
                    const response = await bpsFetch("/api/bps/upload_tracker_icon", {
                        method: "POST",
                        body: uploadData,
                    });
                    if (!response.ok) {
                        bpsToast("Could not upload icon.");
                        return;
                    }
                    const payload = await response.json();
                    if (!payload || !payload.icon_url) {
                        bpsToast("Could not upload icon.");
                        return;
                    }
                    ensureIconOption(payload.icon_url, payload.icon_name || payload.icon_url);
                    if (trackerIconSelector) {
                        trackerIconSelector.value = payload.icon_url;
                    }
                    ensureTrackerIconsStore();
                    finalcords.tracker_icons[activeDevice] = payload.icon_url;
                    savebuttondiv.appendChild(saveButton);
                    if (pollTrackActive && img.naturalWidth > 0) redrawAll();
                    bpsToast("Tracker icon uploaded. Click Save Floor Plan to persist.");
                } catch (error) {
                    console.error("Icon upload failed:", error);
                    bpsToast("Could not upload icon.");
                }
            });
        }
    
    
    // Check if the image is loaded in the canvas
    function checkCanvasImage() {
        if (canvas.width === 0 || canvas.height === 0) {
            bpsToast("Please load a floorplan first.");
            return false;
        }
        return true;
    }

    // Remove all listeners
    function removeListeners(){
        canvas.removeEventListener("mousedown", zoneMouseDown);
        canvas.removeEventListener("mousemove", zoneMouseMove);
        canvas.removeEventListener("mouseup", zoneMouseUp);
        canvas.removeEventListener("contextmenu", zoneUndoPoint);
        canvas.removeEventListener("mousedown", startDrawingScale);
        canvas.removeEventListener("mouseup", endDrawingScale);
        canvas.removeEventListener('click', placeReceiver);
    }

    //Reset all buttons
    function buttonreset(){
        cancelAdjust(); // starting any other tool drops an open adjust preview
        // Clear the value too (not just hide) so a distance typed then abandoned
        // doesn't survive into the next Set Scale session and get saved by accident.
        if (scaleInputElement) {scaleInputElement.style.display = "none"; scaleInputElement.value = "";}
        SetScaleButton.setAttribute('data-active', 'false');
        if (entityInput) {entityInput.style.display = "none";}
        addDeviceButton.setAttribute('data-active', 'false');
        if (zoneInputElement) {zoneInputElement.style.display = "none"; zoneInputElement.value = "";}
        if (zoneCancelBtn) {zoneCancelBtn.style.display = "none";}
        drawAreaButton.setAttribute('data-active', 'false');
        drawSubZoneButton.setAttribute('data-active', 'false');
        focusedReceiver = null;
        messdiv.innerHTML = "";
        // No tool is active after a reset, so hide the map Save/Cancel actions
        // here too. Some reset paths (Clear Canvas, opening the adjust preview)
        // don't follow buttonreset with a drawElements, so the end-of-drawElements
        // sync alone would leave them stranded; hiding here covers those.
        if (mapToolActions) mapToolActions.style.display = "none";
    }

    // Manual zone colour: the swatch beside a zone's name in the sidebar. Fires
    // on 'change' (once the picker commits), stores zone.color, repaints the map
    // + sidebar, and reveals Save so the choice persists.
    document.addEventListener('change', (event) => {
        const el = event.target.closest('[data-type="zonecolor"]');
        if (!el) return;
        // A stale sidebar (e.g. after Clear Canvas) must not fake a save.
        if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const id = el.getAttribute('data-id');
        const zone = floor && (floor.zones || []).find(z => (z.zone_id || z.entity_id) === id);
        if (!zone) return;
        zone.color = el.value;
        zone.uncolored = false; // picking a colour re-enables a removed zone
        savebuttondiv.appendChild(saveButton);
        // Drop focus so the render guard doesn't skip the tree rebuild — the new
        // colour needs to reach the swatch + header tint now that the picker is done.
        el.blur();
        clearCanvas();
        drawElements(); // repaints the map and re-renders the sidebar header tint
        bpsToast("Zone colour updated — Save Floor Plan to keep it.");
    });

    document.addEventListener('click', (event) => {
        // Check if the clicked element has the attribute data-type="removerec"
        if (event.target.closest('[data-type="removerec"]')) {
            const idToRemove = event.target.closest('[data-type="removerec"]').getAttribute('data-id');
            // A stale sidebar (e.g. after Clear Canvas) must not fake a save.
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            bpsConfirm(`Remove receiver "${idToRemove}"?`, { confirmText: "Remove", danger: true }).then(ok => {
                if (!ok) return;
                finalcords.floor.forEach(floor => {
                    if (sameFloorName(floor.name, SelMapName)) {
                        floor.receivers = floor.receivers.filter(receiver => receiver.entity_id !== idToRemove);
                    }
                });
                console.log(`Removed receiver "${idToRemove}"`);
                savebuttondiv.appendChild(saveButton);
                clearCanvas();
                drawElements(); // re-renders the sidebar tree too
            });
            return;
        }
        // Ruler button on a receiver row: set/clear its mount height (m above
        // this floor). Checked before focusrec so editing never focuses.
        if (event.target.closest('[data-type="recheight"]')) {
            const recId = event.target.closest('[data-type="recheight"]').getAttribute('data-id');
            // A stale sidebar (e.g. after Clear Canvas) must not fake a save.
            const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const rec = floor && (floor.receivers || []).find(r => r && r.entity_id === recId);
            if (!rec) return;
            bpsPromptNumber(
                `Mount height of "${recId}" above this floor, in metres (empty = unknown). `
                + `Used to remove the vertical leg from its distances and to judge calibration `
                + `against the true 3D distance — recalibrate after changing it.`,
                { initial: Number.isFinite(rec.height) ? rec.height : "", placeholder: "e.g. 2.2" }
            ).then(val => {
                if (val === undefined) return;                       // cancelled
                if (val === null) delete rec.height; else rec.height = val;
                savebuttondiv.appendChild(saveButton);               // reveal Save Floor Plan
                clearCanvas();
                drawElements();                                      // re-renders the sidebar badge
                bpsToast(val === null
                    ? `Height of "${recId}" cleared — Save Floor Plan to keep it, then recalibrate.`
                    : `Height of "${recId}" set to ${val} m — Save Floor Plan to keep it, then recalibrate.`);
            });
            return;
        }
        // Clicking a receiver row focuses it on the map (only that receiver and
        // its circle stay visible); clicking it again clears the focus. Mirrors
        // clicking the receiver's icon on the map. Checked after removerec so
        // the trash button deletes rather than focuses.
        if (event.target.closest('[data-type="focusrec"]')) {
            const recId = event.target.closest('[data-type="focusrec"]').getAttribute('data-id');
            focusedReceiver = recId === focusedReceiver ? null : recId;
            focusedRecDistLink = null; // a receiver focus supersedes a single-link highlight
            redrawAll();
            return;
        }
        // Re-link a mismatched placement to a live scanner slug (issue #64):
        // rename its entity_id + record the scanner's hardware token, then reveal
        // Save. Only its name changes — position and everything else stay.
        if (event.target.closest('[data-type="relinkrec"]')) {
            const el = event.target.closest('[data-type="relinkrec"]');
            const oldId = el.getAttribute('data-id');
            const newId = el.getAttribute('data-target');
            if (!newId || newId === oldId) return;
            // A stale sidebar (e.g. after Clear Canvas) must not fake a save.
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            let changed = false;
            finalcords.floor.forEach(f => (f.receivers || []).forEach(r => {
                if (r && r.entity_id === oldId) {
                    r.entity_id = newId;
                    r.scanner_uid = scannerTokenJs(newId);
                    changed = true;
                }
            }));
            if (changed) {
                savebuttondiv.appendChild(saveButton);
                clearCanvas();
                drawElements(); // re-renders the tree + scanner issues
                bpsToast(`Re-linked "${oldId}" → "${newId}". Save Floor Plan to keep it.`);
            }
            return;
        }
        // Debugging tab Refresh — re-fetch the receiver-linking snapshot (issue #64).
        if (event.target.closest('[data-type="refreshlinking"]')) {
            if (!scannerLinkingLoading) loadScannerLinking();
            return;
        }
        // Debugging-tab sub-tabs (Receivers / Beacons) — re-render the active view.
        if (event.target.closest('[data-type="debugsubtab"]')) {
            const tab = event.target.closest('[data-type="debugsubtab"]').getAttribute('data-tab');
            if (tab && tab !== debugSubtab) { debugSubtab = tab; renderDebugView(); }
            return;
        }
        if (event.target.closest('[data-type="removezone"]')) {
            const idToRemove = event.target.closest('[data-type="removezone"]').getAttribute('data-id');
            // A stale sidebar (e.g. after Clear Canvas) must not fake a save.
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            const cf = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const zObj = cf && (cf.zones || []).find(z => (z.zone_id || z.entity_id) === idToRemove);
            const zName = zObj ? zObj.entity_id : "this zone";
            const subCount = zObj && Array.isArray(cf.subzones)
                ? cf.subzones.filter(s => s.parent === (zObj.zone_id || zObj.entity_id)).length : 0;
            const msg = subCount
                ? `Remove zone "${zName}" and its ${subCount} sub-zone(s)?`
                : `Remove zone "${zName}"?`;
            bpsConfirm(msg, { confirmText: "Remove", danger: true }).then(ok => {
                if (!ok) return;
                cancelAdjust(); // an open adjust preview is stale once a zone is deleted
                // Loop through each floor and remove zones where the internal zone id matches
                finalcords.floor.forEach(floor => {
                    if (sameFloorName(floor.name, SelMapName)) {
                        const removed = (floor.zones || []).find(zone => (zone.zone_id || zone.entity_id) === idToRemove);
                        floor.zones = floor.zones.filter(zone => (zone.zone_id || zone.entity_id) !== idToRemove);
                        // A sub-zone can't outlive the zone it sits in (matched by
                        // stable id, so a same-named sibling zone keeps its own).
                        if (removed && Array.isArray(floor.subzones)) {
                            floor.subzones = floor.subzones.filter(s => s.parent !== (removed.zone_id || removed.entity_id));
                        }
                    }
                });
                // Drop the deleted zone's expand state so its (unique) id
                // doesn't linger in the set.
                expandedZones.delete(idToRemove);
                console.log(`Removed zone "${idToRemove}"`);
                savebuttondiv.appendChild(saveButton);
                clearCanvas();
                drawElements(); // re-renders the sidebar tree too
            });
            return;
        }
        if (event.target.closest('[data-type="removesubzone"]')) {
            const idToRemove = event.target.closest('[data-type="removesubzone"]').getAttribute('data-id');
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            const cf = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const sObj = cf && (cf.subzones || []).find(s => (s.sub_zone_id || s.entity_id) === idToRemove);
            const sName = sObj ? sObj.entity_id : "this sub-zone";
            bpsConfirm(`Remove sub-zone "${sName}"?`, { confirmText: "Remove", danger: true }).then(ok => {
                if (!ok) return;
                cancelAdjust(); // an open adjust preview is stale once a sub-zone is deleted
                finalcords.floor.forEach(floor => {
                    if (sameFloorName(floor.name, SelMapName) && Array.isArray(floor.subzones)) {
                        floor.subzones = floor.subzones.filter(s => (s.sub_zone_id || s.entity_id) !== idToRemove);
                    }
                });
                console.log(`Removed sub-zone "${idToRemove}"`);
                savebuttondiv.appendChild(saveButton);
                clearCanvas();
                drawElements();
            });
            return;
        }
        if (event.target.closest('[data-type="editzone"]')) {
            const idToEdit = event.target.closest('[data-type="editzone"]').getAttribute('data-id');
            const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const zone = floor && (floor.zones || []).find(z => (z.zone_id || z.entity_id) === idToEdit);
            if (zone) beginEditZone(zone);
        }
        // Toggle a zone's colour on/off (colouring is optional; removing it drops
        // the map tint + header overlay and makes any sub-zones fall back to their
        // own vibrant colour).
        if (event.target.closest('[data-type="zonetogglecolor"]')) {
            const id = event.target.closest('[data-type="zonetogglecolor"]').getAttribute('data-id');
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const zone = floor && (floor.zones || []).find(z => (z.zone_id || z.entity_id) === id);
            if (!zone) return;
            zone.uncolored = !zone.uncolored;
            savebuttondiv.appendChild(saveButton);
            clearCanvas();
            drawElements();
            return;
        }
        // Toggle a zone as no-go dead space (issue #60): the tracker can't be
        // here, so the backend down-weights any floor whose fit lands inside
        // it and snaps a position out to the nearest real zone.
        if (event.target.closest('[data-type="zonetogglenogo"]')) {
            const id = event.target.closest('[data-type="zonetogglenogo"]').getAttribute('data-id');
            if (!finalcords.floor.some(f => sameFloorName(f.name, SelMapName))) return;
            const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const zone = floor && (floor.zones || []).find(z => (z.zone_id || z.entity_id) === id);
            if (!zone) return;
            if (zone.no_go) delete zone.no_go; else zone.no_go = true;
            savebuttondiv.appendChild(saveButton);
            clearCanvas();
            drawElements();
            bpsToast(zone.no_go
                ? `"${zone.entity_id}" marked no-go — Save Floor Plan to keep it.`
                : `"${zone.entity_id}" is no longer no-go — Save Floor Plan to keep it.`);
            return;
        }
        if (event.target.closest('[data-type="editsubzone"]')) {
            const idToEdit = event.target.closest('[data-type="editsubzone"]').getAttribute('data-id');
            const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
            const sub = floor && (floor.subzones || []).find(s => (s.sub_zone_id || s.entity_id) === idToEdit);
            if (sub) beginEditSubZone(sub);
        }
        // Collapse/expand a sidebar zone group. The head also holds the zone's
        // edit/remove buttons, so ignore clicks that landed on an icon button
        // (those run their own handlers above). Toggle the class directly rather
        // than re-rendering so it stays smooth mid-tracking; the next full render
        // reads expandedZones and stays consistent.
        const zoneHead = event.target.closest('[data-type="togglezone"]');
        if (zoneHead && !event.target.closest('.bps-icon-btn') && !event.target.closest('.bps-zone-swatch')) {
            const key = zoneHead.getAttribute('data-key');
            if (expandedZones.has(key)) expandedZones.delete(key);
            else expandedZones.add(key);
            const group = zoneHead.closest('.bps-zone-group');
            if (group) group.classList.toggle('bps-collapsed', !expandedZones.has(key));
            return;
        }
        if (event.target.closest('[data-type="collapse"]')) {
            const collapseDiv = event.target.closest('[data-type="collapse"]');
            const parent = collapseDiv.closest('.fixed'); // Find the nearest parent element to collapseDiv
        
            // Toggle between minimized and normal size
            if (parent.classList.contains('collapsed')) {
                // Reset size
                parent.classList.remove('collapsed');
                parent.style.maxHeight = '80vh'; // Reset height
                parent.querySelectorAll('.space-y-4, #message').forEach(el => {
                    el.style.display = ''; // Show element
                });
            } else {
                // Minimize
                parent.classList.add('collapsed');
                const computedStyleCD = window.getComputedStyle(collapseDiv);
                const computedStyleP = window.getComputedStyle(parent);
                const newheight = parseFloat(computedStyleCD.height) + parseFloat(computedStyleP.paddingTop) + parseFloat(computedStyleP.paddingBottom) - parseFloat(computedStyleCD.paddingBottom);
                parent.style.maxHeight = `${newheight}px`; // Adjust height to collapseDiv
                parent.querySelectorAll('.space-y-4, #message').forEach(el => {
                    el.style.display = 'none'; // Hide element
                });
            }
        }
    });

    // =================================================================
    // Clear canvas functionality
    // =================================================================

    clearCanvasButton.addEventListener('click', () => {
        if (!checkCanvasImage()) return;
        removeListeners();
        drawAreaButton.remove();
        drawSubZoneButton.remove();
        addDeviceButton.remove();
        clearCanvasButton.remove();
        SetScaleButton.remove();
        adjustZonesButton.remove();
        adjustSubZonesButton.remove();
        saveButton.remove();
        deleteButton.remove();
        view.zoom = 1;
        view.x = 0;
        view.y = 0;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        mapname.value = "";
        SelMapName = "";
        buttonreset();
        mapSelector.selectedIndex = 0;
        renderEntityTree(null);
        const issues = document.getElementById("scannerissues");
        if (issues) issues.innerHTML = ""; // clear stale mismatch warnings + Re-link buttons
        // No floor is loaded now, so drop the floor-scoped "not reporting" heads-up
        // (Clear Canvas doesn't route through drawElements, which would re-scope it).
        const linking = document.getElementById("scannerlinking");
        if (linking) linking.innerHTML = "";
    });

    function clearCanvas(){
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.setTransform(view.zoom, 0, 0, view.zoom, view.x, view.y);
        if (mapReady()) {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
        messdiv.innerHTML = "";
    }

    // =================================================================
    // Draw zones
    // =================================================================

    // Zones are polygons: click to add vertices, drag a vertex to move it,
    // drag the shape's inside to move the whole zone. Legacy zones (from the
    // old rectangle tool) stored their four corners in scan order; new zones
    // carry poly: true and keep the order they were drawn in.
    let zonePoints = [];
    let selectedVertex = null;
    let draggingZone = false;
    let dragLast = null;
    let zoneInputElement = null; // För att hantera input-fältet
    let zoneCancelBtn = null; // floating X that cancels the current draw/edit
    // What the polygon editor is currently building/editing:
    //   {kind:'zone'|'subzone', id:<existing id|null>, parent, parentPoints, color}
    // New zones/sub-zones have id null; sidebar "edit" loads an existing id.
    let editTarget = null;

    const handleSize = 15;
    const MAX_ZONE_POINTS = 12; // corner cap for a zone or sub-zone

    // Points in drawable perimeter order for both formats.
    function zonePerimeterPoints(zone) {
        const pts = zone.cords || [];
        if (!zone.poly && pts.length === 4) {
            return [pts[0], pts[1], pts[3], pts[2]]; // legacy TL,TR,BL,BR
        }
        return pts;
    }

    function pointInPolygon(x, y, pts) {
        let inside = false;
        for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
            const intersects = (pts[i].y > y) !== (pts[j].y > y)
                && x < ((pts[j].x - pts[i].x) * (y - pts[i].y)) / (pts[j].y - pts[i].y) + pts[i].x;
            if (intersects) inside = !inside;
        }
        return inside;
    }

    function zoneMousePos(event) {
        const world = worldFromEvent(event);
        return {
            x: Math.max(0, Math.min(canvas.width, world.x)),
            y: Math.max(0, Math.min(canvas.height, world.y)),
        };
    }

    const createSubZoneId = () => `subzone_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    // Each sub-zone gets its own hue so overlapping ones stay distinguishable.
    // Vibrant (high saturation) so sub-zones stand out against zones' faint tint.
    function randomZoneColor() {
        return `hsl(${Math.floor(Math.random() * 360)}, 95%, 50%)`;
    }

    // Nearest point on segment ab to p.
    function projectPointToSegment(p, a, b) {
        const dx = b.x - a.x, dy = b.y - a.y;
        const len2 = dx * dx + dy * dy;
        if (len2 === 0) return { x: a.x, y: a.y };
        let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
        t = Math.max(0, Math.min(1, t));
        return { x: a.x + t * dx, y: a.y + t * dy };
    }

    // Keep a point inside a polygon: unchanged when inside, else projected onto
    // the nearest edge. This is how a sub-zone corner is stopped from leaving
    // its parent zone (the client-side mirror of the backend's snap-into-zone).
    function clampPointToPolygon(pt, polyPts) {
        if (!polyPts || polyPts.length < 3) return pt;
        if (pointInPolygon(pt.x, pt.y, polyPts)) return pt;
        let best = null, bestD = Infinity;
        for (let i = 0, j = polyPts.length - 1; i < polyPts.length; j = i++) {
            const proj = projectPointToSegment(pt, polyPts[j], polyPts[i]);
            const d = Math.hypot(proj.x - pt.x, proj.y - pt.y);
            if (d < bestD) { bestD = d; best = proj; }
        }
        return best || pt;
    }

    // A sub-zone's points are constrained to its parent zone; a main zone's are
    // only clamped to the canvas (already done by zoneMousePos).
    function constrainForEdit(pos) {
        if (editTarget && editTarget.kind === 'subzone' && editTarget.parentPoints) {
            return clampPointToPolygon(pos, editTarget.parentPoints);
        }
        return pos;
    }

    // True when p is inside the polygon or essentially on its edge. Used for
    // whole-shape sub-zone drags: a strict inside test would reject the move as
    // soon as any corner sits on the parent boundary (which clamping puts there),
    // so a sub-zone traced along a wall could never be moved.
    function insideOrOnParent(p, poly) {
        if (!poly) return true;
        const c = clampPointToPolygon(p, poly);
        return Math.hypot(c.x - p.x, c.y - p.y) <= 0.75;
    }

    // Topmost saved zone (last drawn) whose polygon contains pos.
    function hitZoneAt(pos) {
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        if (!floor) return null;
        const zones = floor.zones || [];
        for (let i = zones.length - 1; i >= 0; i--) {
            const pts = zonePerimeterPoints(zones[i]);
            if (pts.length >= 3 && pointInPolygon(pos.x, pos.y, pts)) return zones[i];
        }
        return null;
    }

    function attachZoneHandlers() {
        canvas.addEventListener("mousedown", zoneMouseDown);
        canvas.addEventListener("mousemove", zoneMouseMove);
        canvas.addEventListener("mouseup", zoneMouseUp);
        canvas.addEventListener("contextmenu", zoneUndoPoint);
    }

    drawAreaButton.addEventListener("click", () => {
        if (!checkCanvasImage()) return;
        // The tool button only STARTS the tool; the map's ✓ Save / ✕ Cancel
        // commit or discard. Re-clicking while active is a no-op (don't reset).
        if (drawAreaButton.dataset.active === 'true') return;
        removeListeners();
        clearCanvas();
        drawElements();
        buttonreset();
        zonePoints = [];
        selectedVertex = null;
        draggingZone = false;
        editTarget = { kind: 'zone', id: null };
        attachZoneHandlers();
        drawAreaButton.setAttribute('data-active', 'true');
        // Repaint now the tool is active so receivers drop out immediately
        // (the repaint above ran before data-active flipped).
        clearCanvas(); drawElements();
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Instructions</h4><p class="text-sm text-gray-500">Click the floor image to place the zone\'s corners, one by one — any shape with three or more corners works. Drag a corner to adjust it, or drag the inside of the zone to move the whole zone. Right-click a corner to delete it. Enter the zone name (matching your Home Assistant areas is a good idea), then press ✓ Save. Press Esc or ✕ Cancel to back out.</p>';
    });

    // Sub-zone tool: draw a polygon inside a chosen parent zone (a couch, a
    // desk). Shares the polygon editor with Draw Zone; the difference is a
    // parent that every corner is clamped inside, and a random color.
    drawSubZoneButton.addEventListener("click", () => {
        if (!checkCanvasImage()) return;
        if (drawSubZoneButton.dataset.active === 'true') return; // active: use ✓ Save / ✕ Cancel
        const floor = finalcords.floor.find(f => sameFloorName(f.name, mapname.value));
        if (!floor || !((floor.zones || []).length)) {
            bpsToast("Draw at least one zone first — a sub-zone is placed inside a zone.");
            return;
        }
        removeListeners();
        clearCanvas();
        drawElements();
        buttonreset();
        zonePoints = [];
        selectedVertex = null;
        draggingZone = false;
        editTarget = { kind: 'subzone', id: null, parent: null, parentPoints: null, color: randomZoneColor() };
        attachZoneHandlers();
        drawSubZoneButton.setAttribute('data-active', 'true');
        // Repaint now the tool is active so receivers drop out immediately.
        clearCanvas(); drawElements();
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Instructions</h4><p class="text-sm text-gray-500">Click inside the zone you want to add a sub-zone to — that becomes its parent — then keep clicking to place corners (they stay inside the parent). Drag a corner to adjust it, drag the inside to move it, right-click a corner to delete it. Name it (e.g. Couch), then press ✓ Save. Press Esc or ✕ Cancel to back out.</p>';
    });

    // Commit the polygon in the editor into finalcords: add a new zone/sub-zone,
    // or update the existing one when editTarget.id is set.
    function finalizeShape() {
        if (!mapname.value) { bpsToast("Please enter a floor name!"); return false; }
        SelMapName = mapname.value;
        const isSub = !!(editTarget && editTarget.kind === 'subzone');
        if (zonePoints.length < 3) {
            bpsToast((isSub ? "A sub-zone" : "A zone") + " needs at least three corners.");
            return false;
        }
        const nameEl = document.getElementById('zoneName');
        const name = (nameEl ? nameEl.value : "").trim();
        if (!name) { bpsToast("Please provide a name."); return false; }
        const cords = zonePoints.map(p => ({ x: p.x, y: p.y }));
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));

        if (isSub) {
            if (!editTarget.parent) { bpsToast("Click inside a zone first to choose the sub-zone's parent."); return false; }
            if (!floor) { bpsToast("Select a floor first."); return false; }
            if (!Array.isArray(floor.subzones)) floor.subzones = [];
            if (editTarget.id) {
                const sz = floor.subzones.find(s => (s.sub_zone_id || s.entity_id) === editTarget.id);
                if (sz) { sz.entity_id = name; sz.cords = cords; sz.parent = editTarget.parent; sz.poly = true; }
            } else {
                floor.subzones.push({
                    sub_zone_id: createSubZoneId(),
                    entity_id: name,
                    parent: editTarget.parent,
                    poly: true,
                    color: editTarget.color || randomZoneColor(),
                    cords,
                });
            }
            savebuttondiv.appendChild(saveButton);
            bpsToast(`Sub-zone saved: ${name}`);
            return true;
        }

        // Main zone: update in place when editing, else add a new one.
        if (editTarget && editTarget.id) {
            const z = floor && (floor.zones || []).find(zz => (zz.zone_id || zz.entity_id) === editTarget.id);
            if (z) { z.entity_id = name; z.cords = cords; z.poly = true; }
            savebuttondiv.appendChild(saveButton);
            bpsToast(`Zone saved: ${name}`);
            return true;
        }
        zoneName = name;
        const newZone = { zone_id: createZoneId(), entity_id: name, poly: true, cords };
        if (addDataToFloor(finalcords, SelMapName, "zones", newZone)) {
            bpsToast(`Zone saved: ${name}`);
            return true;
        }
        return false;
    }

    // Discard the in-progress draw/edit without writing anything to finalcords
    // (an edit works on a copy of the points, so the original is untouched).
    function cancelShapeEdit() {
        removeListeners();
        buttonreset();
        zonePoints = [];
        selectedVertex = null;
        draggingZone = false;
        editTarget = null;
        clearCanvas();
        drawElements();
    }

    // A layout tool that draws on the map is active (draw/edit zone or sub-zone,
    // set scale, place receiver). Used to show the Cancel button and gate Esc.
    function anyLayoutToolActive() {
        return drawAreaButton.dataset.active === 'true'
            || drawSubZoneButton.dataset.active === 'true'
            || SetScaleButton.dataset.active === 'true'
            || addDeviceButton.dataset.active === 'true';
    }

    // Back out of whichever layout tool is active, discarding the in-progress
    // zone/sub-zone/scale/receiver — usable at any point, including before the
    // first corner/dot (where no floating ✕ exists yet). Reached from the ✕
    // Cancel button on the map and from the Esc key.
    function cancelActiveTool() {
        if (!anyLayoutToolActive()) return;
        removeListeners();
        buttonreset();          // resets tool buttons + hides the floating inputs/✕
        zonePoints = [];
        selectedVertex = null;
        draggingZone = false;
        editTarget = null;
        startPoint = null;
        endPoint = null;
        countclick = 0;         // reset the scale click toggle so the next session starts fresh
        tmpcords = null;
        receiverName = "";
        clearCanvas();
        drawElements();         // repaints with all tools off; also hides the Cancel button
    }
    if (cancelToolBtn) cancelToolBtn.addEventListener('click', cancelActiveTool);
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        // A confirm dialog owns Esc while open — don't also cancel the tool.
        if (document.querySelector('.bps-modal-overlay')) return;
        if (anyLayoutToolActive()) cancelActiveTool();
    });

    // Commit the active layout tool — the map's green ✓ Save button (the tool
    // buttons themselves only start a tool now, they no longer double as Save).
    // Each commit validates and, on success, tears down (removeListeners +
    // buttonreset + repaint); on failure it toasts and leaves the tool active.
    function finalizeShapeAndReset() {
        if (finalizeShape()) {
            removeListeners();
            buttonreset();
            if (zoneInputElement) zoneInputElement.value = "";
            zonePoints = [];
            editTarget = null;
            clearCanvas();
            drawElements();
        }
    }
    function saveReceiver() {
        if (!mapname.value) { bpsToast("Floor name must be set."); return; }
        SelMapName = mapname.value;
        receiverName = getPickedReceiverName();
        if (!tmpcords || !Number.isFinite(tmpcords.x) || !Number.isFinite(tmpcords.y)) {
            bpsToast("Receiver coordinates must be set — click the floorplan first.");
            return;
        }
        if (!receiverName) {
            bpsToast("Select a receiver from the list (or pick Custom name… and type one).");
            return;
        }
        const newReceiver = { entity_id: receiverName, cords: tmpcords };
        // Optional mount height (m). Empty = unknown: distances stay slant
        // ranges and calibration truth stays 2D, exactly as before.
        // badInput = unparsable content reading back as "": reject it rather
        // than silently placing the receiver without the height typed in.
        if (receiverHeightInput && receiverHeightInput.validity.badInput) {
            bpsToast("Mount height must be a number between 0 and 10 metres.");
            return;
        }
        const heightRaw = receiverHeightInput ? receiverHeightInput.value.trim() : "";
        if (heightRaw !== "") {
            const h = parseFloat(heightRaw);
            if (!Number.isFinite(h) || h < 0 || h > 10) {
                bpsToast("Mount height must be a number between 0 and 10 metres.");
                return;
            }
            newReceiver.height = h;
        }
        // Committing: drop the placement click listener up front. On a duplicate
        // name addDataToFloor itself toasts + resets the UI and returns false, so
        // removing here (not only in the success branch) avoids stranding the
        // listener while the tool already looks inactive.
        removeListeners();
        if (addDataToFloor(finalcords, SelMapName, "receivers", newReceiver)) {
            buttonreset();
            clearCanvas();
            drawElements();
        }
    }
    function saveActiveTool() {
        if (drawAreaButton.dataset.active === 'true' || drawSubZoneButton.dataset.active === 'true') {
            finalizeShapeAndReset();
        } else if (SetScaleButton.dataset.active === 'true') {
            saveScale();
        } else if (addDeviceButton.dataset.active === 'true') {
            saveReceiver();
        }
    }
    if (saveToolBtn) saveToolBtn.addEventListener('click', saveActiveTool);

    // Header toggle: turn every zone's colour on or off at once. If any zone is
    // currently coloured, this removes them all; if all are already removed, it
    // restores them.
    if (zoneColorsToggle) zoneColorsToggle.addEventListener('click', () => {
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const zones = (floor && floor.zones) || [];
        if (!zones.length) return;
        const anyColored = zones.some(z => !z.uncolored);
        zones.forEach(z => { z.uncolored = anyColored; });
        savebuttondiv.appendChild(saveButton);
        clearCanvas();
        drawElements();
    });

    // Load a saved zone/sub-zone into the polygon editor (reusing the draw
    // machinery); the matching tool button flips to its "Save" state so the
    // next click on it commits the edit in place.
    function beginEditZone(zone) {
        if (!checkCanvasImage()) return;
        removeListeners();
        buttonreset();
        SelMapName = mapname.value || SelMapName;
        zonePoints = zonePerimeterPoints(zone).map(p => ({ x: p.x, y: p.y }));
        selectedVertex = null;
        draggingZone = false;
        editTarget = { kind: 'zone', id: zone.zone_id || zone.entity_id };
        attachZoneHandlers();
        drawAreaButton.setAttribute('data-active', 'true');
        drawZonePreview();
        const zn = document.getElementById('zoneName');
        if (zn) zn.value = zone.entity_id || "";
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Editing zone</h4><p class="text-sm text-gray-500">Drag a corner to move it, drag the inside to move the whole zone, right-click a corner to delete it, or click empty space to add one. Press ✓ Save to keep the changes.</p>';
    }

    function beginEditSubZone(sub) {
        if (!checkCanvasImage()) return;
        removeListeners();
        buttonreset();
        SelMapName = mapname.value || SelMapName;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const parentZone = floor && (floor.zones || []).find(z => (z.zone_id || z.entity_id) === sub.parent);
        zonePoints = (sub.cords || []).map(p => ({ x: p.x, y: p.y }));
        selectedVertex = null;
        draggingZone = false;
        editTarget = {
            kind: 'subzone',
            id: sub.sub_zone_id || sub.entity_id,
            parent: sub.parent,
            parentPoints: parentZone ? zonePerimeterPoints(parentZone).map(p => ({ x: p.x, y: p.y })) : null,
            color: sub.color || randomZoneColor(),
        };
        attachZoneHandlers();
        drawSubZoneButton.setAttribute('data-active', 'true');
        drawZonePreview();
        const zn = document.getElementById('zoneName');
        if (zn) zn.value = sub.entity_id || "";
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Editing sub-zone</h4><p class="text-sm text-gray-500">Corners stay inside the parent zone. Drag a corner, drag the inside to move it, right-click a corner to delete it. Press ✓ Save to keep the changes.</p>';
    }

    function zoneMouseDown(event) {
        if (event.button !== 0) return; // left button only; right-click deletes via zoneUndoPoint
        const pos = zoneMousePos(event);

        // Sub-zone: the first click chooses the parent zone and seeds corner 1.
        if (editTarget && editTarget.kind === 'subzone' && !editTarget.parent) {
            const parent = hitZoneAt(pos);
            if (!parent) { bpsToast("Click inside the zone you want to add a sub-zone to."); return; }
            if (!parent.zone_id) parent.zone_id = createZoneId();
            editTarget.parent = parent.zone_id; // stable id, survives renames / same-named zones
            editTarget.parentPoints = zonePerimeterPoints(parent).map(p => ({ x: p.x, y: p.y }));
            zonePoints = [clampPointToPolygon(pos, editTarget.parentPoints)];
            drawZonePreview();
            return;
        }

        selectedVertex = null;
        draggingZone = false;

        for (let i = 0; i < zonePoints.length; i++) {
            if (Math.hypot(zonePoints[i].x - pos.x, zonePoints[i].y - pos.y) <= handleSize * 2) {
                selectedVertex = i;
                return;
            }
        }
        if (zonePoints.length >= 3 && pointInPolygon(pos.x, pos.y, zonePoints)) {
            draggingZone = true;
            dragLast = pos;
            return;
        }
        if (zonePoints.length >= MAX_ZONE_POINTS) {
            bpsToast(`A zone or sub-zone can have at most ${MAX_ZONE_POINTS} corners.`);
            return;
        }
        zonePoints.push(constrainForEdit(pos));
        drawZonePreview();
    }

    function zoneMouseMove(event) {
        if (selectedVertex === null && !draggingZone) return;
        const pos = zoneMousePos(event);

        if (selectedVertex !== null) {
            zonePoints[selectedVertex] = constrainForEdit(pos);
        } else if (draggingZone) {
            let dx = pos.x - dragLast.x;
            let dy = pos.y - dragLast.y;
            if (editTarget && editTarget.kind === 'subzone' && editTarget.parentPoints) {
                // Move only if every corner stays inside the parent zone, so the
                // sub-zone keeps its shape and never leaks out of its parent.
                const moved = zonePoints.map(p => ({ x: p.x + dx, y: p.y + dy }));
                if (moved.every(p => insideOrOnParent(p, editTarget.parentPoints))) {
                    zonePoints = moved;
                    dragLast = pos;
                }
            } else {
                // Main zone: clamp the translation so no corner can leave the
                // canvas — a corner outside the visible area can't be grabbed.
                const xs = zonePoints.map(p => p.x);
                const ys = zonePoints.map(p => p.y);
                dx = Math.max(-Math.min(...xs), Math.min(canvas.width - Math.max(...xs), dx));
                dy = Math.max(-Math.min(...ys), Math.min(canvas.height - Math.max(...ys), dy));
                zonePoints = zonePoints.map(p => ({ x: p.x + dx, y: p.y + dy }));
                dragLast = pos;
            }
        }
        drawZonePreview();
    }

    function zoneMouseUp() {
        selectedVertex = null;
        draggingZone = false;
        dragLast = null;
    }

    function zoneUndoPoint(event) {
        event.preventDefault();
        if (!zonePoints.length) return;
        const pos = zoneMousePos(event);
        let idx = -1;
        for (let i = 0; i < zonePoints.length; i++) {
            if (Math.hypot(zonePoints[i].x - pos.x, zonePoints[i].y - pos.y) <= handleSize * 2) {
                idx = i;
                break;
            }
        }
        if (idx < 0) {
            // Missed every handle: while drawing a NEW shape this undoes the last
            // placed corner; when editing an existing shape a stray right-click
            // off a corner does nothing.
            if (!(editTarget && !editTarget.id)) return;
            idx = zonePoints.length - 1;
        }
        zonePoints.splice(idx, 1);
        // Deleting the very last corner cancels the whole add/edit; anything
        // above that just removes the clicked corner (you can go below three
        // while editing — Save still requires three).
        if (!zonePoints.length) {
            cancelShapeEdit();
            return;
        }
        drawZonePreview();
    }

    function drawZonePreview() {
        clearCanvas();
        drawElements();

        // Create the input field and place it above the zone
        if (!zoneInputElement) {
            zoneInputElement = document.createElement("input");
            zoneInputElement.type = "text";
            zoneInputElement.id = "zoneName";
            zoneInputElement.placeholder = "Name";
            zoneInputElement.classList.add("zone-input");
            document.body.appendChild(zoneInputElement);
        }
        if (!zoneCancelBtn) {
            zoneCancelBtn = document.createElement("button");
            zoneCancelBtn.type = "button";
            zoneCancelBtn.textContent = "✕";
            zoneCancelBtn.title = "Cancel (discard this zone / sub-zone)";
            zoneCancelBtn.classList.add("zone-cancel-btn");
            zoneCancelBtn.addEventListener("click", cancelShapeEdit);
            document.body.appendChild(zoneCancelBtn);
        }

        if (!zonePoints.length) {
            zoneInputElement.style.display = "none";
            zoneCancelBtn.style.display = "none";
            return;
        }

        // Show first so offsetWidth/Height are measurable, then position.
        zoneInputElement.style.position = "absolute";
        zoneInputElement.style.display = "block";
        zoneCancelBtn.style.position = "absolute";
        zoneCancelBtn.style.display = "block";

        const cx = zonePoints.reduce((s, p) => s + p.x, 0) / zonePoints.length;
        const topY = Math.min(...zonePoints.map(p => p.y));
        const botY = Math.max(...zonePoints.map(p => p.y));

        // Keep the name field (+ its ✕) ON the map. Prefer just above the zone;
        // if that would clip off the top of the map, drop it just below the
        // zone instead; and if the zone spans the whole map height, clamp it
        // inside as a last resort. Also clamp horizontally so an edge zone's
        // field never spills off the side (issue: name field shown off-map).
        const rect = canvas.getBoundingClientRect();
        const mapLeft = rect.left + window.scrollX;
        const mapTop = rect.top + window.scrollY;
        const M = 6; // margin from the map edges
        const groupW = zoneInputElement.offsetWidth + 4 + zoneCancelBtn.offsetWidth;
        const groupH = Math.max(zoneInputElement.offsetHeight, zoneCancelBtn.offsetHeight);
        const minTop = mapTop + M;
        const maxTop = mapTop + rect.height - groupH - M;
        const aboveTop = cssFromWorld(cx, topY).top - groupH - M;
        const belowTop = cssFromWorld(cx, botY).top + M;
        let top;
        if (aboveTop >= minTop) top = aboveTop;            // room above the zone
        else if (belowTop <= maxTop) top = belowTop;       // else below the zone
        else top = Math.min(Math.max(aboveTop, minTop), maxTop); // clamp inside

        let left = cssFromWorld(cx, topY).left - 40;
        left = Math.min(Math.max(left, mapLeft + M), mapLeft + rect.width - groupW - M);

        zoneInputElement.style.left = `${left}px`;
        zoneInputElement.style.top = `${top}px`;
        // X button hugging the name field's top-right corner.
        zoneCancelBtn.style.left = `${left + zoneInputElement.offsetWidth + 4}px`;
        zoneCancelBtn.style.top = `${top}px`;

        // Draw the polygon so far
        ctx.beginPath();
        ctx.moveTo(zonePoints[0].x, zonePoints[0].y);
        for (let i = 1; i < zonePoints.length; i++) {
            ctx.lineTo(zonePoints[i].x, zonePoints[i].y);
        }
        const shapeColor = (editTarget && editTarget.kind === 'subzone') ? (editTarget.color || "#3f51b5") : "red";
        if (zonePoints.length >= 3) {
            ctx.closePath();
            ctx.save();
            ctx.globalAlpha = 0.12; // shows where the shape can be dragged
            ctx.fillStyle = shapeColor;
            ctx.fill();
            ctx.restore();
        }
        ctx.strokeStyle = shapeColor;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw handles on every corner
        zonePoints.forEach(point => {
            ctx.beginPath();
            ctx.arc(point.x, point.y, handleSize, 0, Math.PI * 2);
            ctx.fillStyle = shapeColor;
            ctx.fill();
        });
    }

    // =================================================================
    // Set the scale for the floor
    // =================================================================

    let startPoint = null;
    let endPoint = null;
    let scaleInputElement = null; 

    SetScaleButton.addEventListener("click", () => {
        if (!checkCanvasImage()) return;
        if (SetScaleButton.dataset.active === 'true') return; // active: use ✓ Save / ✕ Cancel
        removeListeners();
        clearCanvas();
        drawElements();
        buttonreset();
        startPoint = null;
        endPoint = null;
        countclick = 0; // reset the start/end toggle so a stale "1" (from a prior
                        // session abandoned after the first point) can't skip
                        // setting startPoint and crash the next scale click.

        canvas.addEventListener("mousedown", startDrawingScale);
        canvas.addEventListener("mouseup", endDrawingScale);
        SetScaleButton.setAttribute('data-active', 'true');
        // Repaint now the tool is active so receivers drop out immediately —
        // scale drawing paints the dots/line directly and never calls
        // drawElements, so without this the guard would never run. Set the
        // instructions AFTER this — clearCanvas() blanks the message panel.
        clearCanvas(); drawElements();
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Instructions</h4><p class="text-sm text-gray-500">Set the scale by clicking on the desired starting point and then again on the desired end point. Enter the actual (real-world) distance in the input element, then press ✓ Save. Press Esc or ✕ Cancel to back out.</p>';
    });

    let countclick = 0;
    function startDrawingScale(event) {
        if(countclick === 0){
            startPoint = worldFromEvent(event);
            isDrawing = false;
            countclick++; // Add one to variable

            //Draw starting point
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'red'; // Set fill color
            ctx.beginPath(); // Draw a circle
            ctx.arc(startPoint.x, startPoint.y, 10, 0, Math.PI * 2); // Rita en cirkel
            ctx.fill(); // Fill circle

            return;
        }
        if(countclick === 1){
            isDrawing = true;
            countclick = 0;
        }
    }

    function endDrawingScale(event) {
        if (!isDrawing) return;
        endPoint = worldFromEvent(event);
        isDrawing = false;

        if (startPoint.x === endPoint.x && startPoint.y === endPoint.y) {
            console.log("No line drawn")
            return;
        }

        ctx.beginPath();
        ctx.moveTo(startPoint.x, startPoint.y);
        ctx.lineTo(endPoint.x, endPoint.y);
        ctx.strokeStyle = "red"; // Make line red
        ctx.lineWidth = 4;       // Set thickness of line
        ctx.stroke();

        // Create input field and place it above line
        if (!scaleInputElement) {
            scaleInputElement = document.createElement("input");
            scaleInputElement.type = "number";
            scaleInputElement.id = "scaleValue";
            scaleInputElement.placeholder = "m";
            scaleInputElement.classList.add("scale-input");
            document.body.appendChild(scaleInputElement);
        }

        const lineMidpoint = {
            x: (startPoint.x + endPoint.x) / 2,
            y: (startPoint.y + endPoint.y) / 2
        };
        
        const css = cssFromWorld(lineMidpoint.x, lineMidpoint.y);

        scaleInputElement.style.left = `${css.left - scaleInputElement.offsetWidth / 2 + 40}px`;
        scaleInputElement.style.top = `${css.top - 40}px`;
        scaleInputElement.style.display = "block";
        scaleInputElement.style.position = "absolute";
        scaleInputElement.style.width = "60px";
    }

    function saveScale() {
        if (!startPoint || !endPoint || startPoint.x === endPoint.x || startPoint.y === endPoint.y) {
            bpsToast("Please draw a line first.");
            return;
        }

        const scaleInput = parseFloat(scaleValue.value);
        if (isNaN(scaleInput) || scaleInput <= 0) {
            bpsToast("Please enter the actual length in meters.");
            return;
        }

        if (!mapname.value) {
            bpsToast("Floor name must be set.");
            return;
        }
        SelMapName = mapname.value;

        const dx = endPoint.x - startPoint.x;
        const dy = endPoint.y - startPoint.y;
        const lineLength = Math.sqrt(dx * dx + dy * dy); // Calculate length of drawn line
        (`Line length: ${lineLength}`);
        
        // Save scale
        myScaleVal = lineLength / scaleInput;
        if(addDataToFloor(finalcords, SelMapName, "scale", myScaleVal)){
            removeListeners(); // tear down the scale mousedown/up handlers
            buttonreset(); //Reset buttons
            clearCanvas(); //Clear canvas
            drawElements(); //Draw elements
        }
    }
    // =================================================================

    // =================================================================
    // Place receiver functionality
    // =================================================================

    let entityInput = null; // Floating receiver picker (search + select + custom input)
    let receiverSelect = null;
    let receiverCustomInput = null;
    let receiverSearchInput = null;
    let receiverHeightInput = null; // optional mount height (m) for the new receiver
    let receiverCancelBtn = null; // X that cancels receiver placement
    let availableReceiverNames = []; // unplaced receiver names, for the search filter
    const CUSTOM_RECEIVER_OPTION = "__custom__";

    function getPickedReceiverName() {
        if (!receiverSelect) return "";
        if (receiverSelect.value === CUSTOM_RECEIVER_OPTION) {
            return receiverCustomInput.value.trim();
        }
        return receiverSelect.value.trim();
    }

    // Abort the Place Receiver flow and discard the pending marker.
    function cancelReceiverPlacement() {
        removeListeners();
        buttonreset(); // resets the Place Receiver button and hides the picker
        tmpcords = null;
        receiverName = "";
        clearCanvas();
        drawElements();
    }

    // Render the receiver <option>s, filtered by the search query. Keeps the
    // placeholder and "Custom name…" entries, and preserves the current pick
    // when it still matches the filter.
    function renderReceiverOptions(query = "") {
        if (!receiverSelect) return;
        const q = query.trim().toLowerCase();
        const prev = receiverSelect.value;
        receiverSelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "-- Select receiver --";
        receiverSelect.appendChild(placeholder);
        availableReceiverNames
            .filter(name => !q || name.toLowerCase().includes(q))
            .forEach(name => {
                const option = document.createElement("option");
                option.value = name;
                option.textContent = name;
                receiverSelect.appendChild(option);
            });
        const custom = document.createElement("option");
        custom.value = CUSTOM_RECEIVER_OPTION;
        custom.textContent = "Custom name…";
        receiverSelect.appendChild(custom);
        if ([...receiverSelect.options].some(o => o.value === prev)) {
            receiverSelect.value = prev;
        } else {
            receiverSelect.value = "";
            if (receiverCustomInput) receiverCustomInput.style.display = "none";
        }
    }

    function populateReceiverSelect() {
        // A receiver physically exists on one floor: placing the same name on
        // several floors makes them compete for the tracker's floor. Hide
        // names placed on ANY floor; "Custom name…" remains the escape hatch.
        const placedAnywhere = new Set();
        if (Array.isArray(finalcords.floor)) {
            finalcords.floor.forEach(floor => {
                (floor.receivers || []).forEach(r => placedAnywhere.add(r.entity_id));
            });
        }
        availableReceiverNames = receiverOptions.filter(name => !placedAnywhere.has(name));
        if (receiverSearchInput) receiverSearchInput.value = "";
        renderReceiverOptions("");
        if (receiverCustomInput) {
            receiverCustomInput.value = "";
            receiverCustomInput.style.display = "none";
        }
        if (receiverHeightInput) receiverHeightInput.value = "";
    }

    addDeviceButton.addEventListener('click', () => {
        if (!checkCanvasImage()) return;
        if (addDeviceButton.dataset.active === 'true') return; // active: use ✓ Save / ✕ Cancel
        removeListeners();
        receiverName = "";
        buttonreset();

        // A new placement session must not inherit coordinates or a
        // picked name from the previous one.
        tmpcords = null;
        if (receiverSelect) populateReceiverSelect();
        canvas.addEventListener('click', placeReceiver);
        addDeviceButton.setAttribute('data-active', 'true');
        // Repaint so receivers show immediately: we may have switched here
        // from a geometry tool that hid them, and Place Receiver needs the
        // existing receivers visible to position the new one. (This handler
        // otherwise never repaints until the first floorplan click.) Set the
        // instructions AFTER this — clearCanvas() blanks the message panel.
        clearCanvas(); drawElements();
        messdiv.innerHTML = '<h4 class="font-medium mb-2">Instructions</h4><p class="text-sm text-gray-500">Place a BLE receiver by clicking its location on the floorplan, then pick it from the list. The list shows every receiver Bermuda currently reports (the part after "_distance_to_" in its sensors); receivers already placed on any floor are hidden, since a receiver belongs to one floor. Pick "Custom name…" to type a name manually, then press ✓ Save. Press Esc or ✕ Cancel to back out.</p>';
    });

    // =================================================================
    // Placera en BLE mottagare
    // =================================================================

    function placeReceiver(event) {

        clearCanvas(); // Remove all drawn elements from canvas
        const pos = zoneMousePos(event);

        drawElements(pos.x, pos.y, "receiver");

        if (!entityInput) {
            entityInput = document.createElement("div");
            entityInput.classList.add("rec-input-wrap");

            receiverSearchInput = document.createElement("input");
            receiverSearchInput.type = "text";
            receiverSearchInput.id = "receiverSearch";
            receiverSearchInput.placeholder = "Search receivers…";
            receiverSearchInput.classList.add("rec-input");
            receiverSearchInput.addEventListener("input", () => renderReceiverOptions(receiverSearchInput.value));

            receiverSelect = document.createElement("select");
            receiverSelect.id = "receiverName";
            receiverSelect.classList.add("rec-input");
            receiverSelect.addEventListener("change", () => {
                const custom = receiverSelect.value === CUSTOM_RECEIVER_OPTION;
                receiverCustomInput.style.display = custom ? "block" : "none";
                if (custom) receiverCustomInput.focus();
            });

            receiverCustomInput = document.createElement("input");
            receiverCustomInput.type = "text";
            receiverCustomInput.id = "receiverCustomName";
            receiverCustomInput.placeholder = "Custom name";
            receiverCustomInput.classList.add("rec-input");
            receiverCustomInput.style.display = "none";

            // Optional mount height (m above this floor). Bermuda distances
            // are slant ranges: with the height known, the backend removes the
            // vertical leg before trilateration and calibration judges the
            // pair against the true 3D distance. Editable later from the
            // receiver's row in the Zones & Receivers sidebar.
            receiverHeightInput = document.createElement("input");
            receiverHeightInput.type = "number";
            receiverHeightInput.id = "receiverHeight";
            receiverHeightInput.placeholder = "Mount height m (optional)";
            receiverHeightInput.min = "0";
            receiverHeightInput.max = "10";
            receiverHeightInput.step = "0.1";
            receiverHeightInput.title = "Height above this floor the receiver is mounted at, in metres";
            receiverHeightInput.classList.add("rec-input");

            receiverCancelBtn = document.createElement("button");
            receiverCancelBtn.type = "button";
            receiverCancelBtn.textContent = "✕";
            receiverCancelBtn.title = "Cancel receiver placement";
            receiverCancelBtn.classList.add("zone-cancel-btn", "rec-cancel-btn");
            receiverCancelBtn.addEventListener("click", cancelReceiverPlacement);

            entityInput.appendChild(receiverSearchInput);
            entityInput.appendChild(receiverSelect);
            entityInput.appendChild(receiverCustomInput);
            entityInput.appendChild(receiverHeightInput);
            entityInput.appendChild(receiverCancelBtn);
            document.body.appendChild(entityInput);
            // Populate only on creation; the session-start populate happens
            // in the Place Receiver activation. Repopulating on every canvas
            // click would wipe the user's pick while repositioning.
            populateReceiverSelect();
        }

        const css = cssFromWorld(pos.x + canvas.width * 0.02, pos.y);
        entityInput.style.left = `${css.left + 8}px`;
        entityInput.style.top = `${css.top - 16}px`;
        entityInput.style.display = "flex";
        entityInput.style.position = "absolute";
    }

    // =================================================================
    // Move existing receivers by dragging them on the map
    // =================================================================

    let dragReceiverRef = null;
    let dragOffset = null;
    let dragMoved = false;
    let panState = null;
    let clickCandidate = null;
    let clickDeviceCandidate = null; // tracked device under the cursor at mousedown
    let clickLinkCandidate = null;   // receiver-distance link "a|b" under the cursor at mousedown
    let focusedReceiver = null;
    // A single receiver-distance link isolated by clicking its line or pill:
    // "a|b" (sorted slugs), or null. When set, only that link's line + pill are
    // drawn; every other line is hidden. Cleared by clicking it again, an empty
    // spot, or a receiver.
    let focusedRecDistLink = null;
    // World-space rects of the receiver-distance lines/pills as last drawn, so
    // the line/pill hit-test matches exactly what is on screen. Rebuilt every
    // drawReceiverDistances; emptied when the overlay draws nothing.
    let recDistDrawn = [];
    // Receiver-distance link "a|b" under the cursor: its distance pill shows on
    // hover (pills are hidden by default to keep a dense floor's overview
    // readable — details on demand).
    let hoveredRecDistLink = null;
    let hoveredReceiver = null; // receiver under the cursor; its name shows (names are hidden otherwise)
    // Sidebar zone groups the user has expanded, keyed by zone id (synthetic
    // "__unzoned__" / "__orphan_subs__" keys for the two special groups). Groups
    // start COLLAPSED on every page load (this set begins empty and is not
    // persisted), so the sidebar opens compact; the user expands the ones they
    // want. Kept outside the DOM so expansions survive the frequent full
    // re-renders of the tree (each tracking tick rebuilds it) within a session.
    const expandedZones = new Set();
    // Which sidebar group a receiver renders under. Mirrors renderEntityTree's
    // greedy assignment: the first zone (in order) whose polygon contains the
    // receiver claims it; otherwise it falls to the per-floor "No zone" group.
    function groupKeyForReceiver(floor, recEntityId) {
        if (!floor) return null;
        const rec = (floor.receivers || []).find(r => r && r.entity_id === recEntityId && r.cords);
        if (!rec) return null;
        for (const zone of (floor.zones || [])) {
            const pts = zonePerimeterPoints(zone);
            if (pts.length >= 3 && pointInPolygon(rec.cords.x, rec.cords.y, pts)) {
                return zone.zone_id || zone.entity_id;
            }
        }
        return `__unzoned__::${floor.name || ""}`;
    }
    // Expand the sidebar group holding a receiver so selecting it on the map
    // reveals it in the list. No-op when the group is already open or the id is
    // null (e.g. clearing focus).
    function expandGroupForReceiver(recEntityId) {
        if (!recEntityId) return;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const key = groupKeyForReceiver(floor, recEntityId);
        if (key) expandedZones.add(key);
    }
    const moveToggle = document.getElementById("moveToggle");
    const viewReset = document.getElementById("viewReset");

    function drawToolActive() {
        return drawAreaButton.dataset.active === 'true'
            || drawSubZoneButton.dataset.active === 'true'
            || addDeviceButton.dataset.active === 'true'
            || SetScaleButton.dataset.active === 'true';
    }

    // Receivers are not drawn while laying out geometry (adjust preview, or
    // drawing/editing a zone/sub-zone, or setting the scale). This is the single
    // source of truth for BOTH rendering and hit-testing, so a receiver is
    // clickable exactly when it is visible. (Place Receiver is excluded: there
    // the receivers stay visible.)
    function receiversHidden() {
        return !!adjustPreview
            || drawAreaButton.dataset.active === 'true'
            || drawSubZoneButton.dataset.active === 'true'
            || SetScaleButton.dataset.active === 'true';
    }

    function hitReceiverAt(pos) {
        // Hidden receivers must not be clickable/draggable — only what's on
        // screen can be hit (mirrors the render guard exactly).
        if (receiversHidden()) return null;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        if (!floor) return null;
        const hitRadius = canvas.width * 0.02 + 10; // icon radius plus slack
        // When one receiver is focused, only what's drawn is hittable: normally
        // just the focused receiver — but with the receiver-distances overlay on,
        // its link neighbours are drawn too (drawReceiverDistances), so clicking
        // one pivots the focus there instead of reading as empty space. A click
        // over anything still hidden clears the focus, as before.
        let candidates = floor.receivers || [];
        if (focusedReceiver) {
            const visible = new Set([focusedReceiver]);
            if (recDistToggle.checked) {
                receiverDistanceLinks().links.forEach(l => {
                    if (l.a === focusedReceiver || l.b === focusedReceiver) {
                        visible.add(l.a);
                        visible.add(l.b);
                    }
                });
            }
            candidates = candidates.filter(r => visible.has(r.entity_id));
        }
        return candidates.find(r =>
            r.cords && Math.hypot(r.cords.x - pos.x, r.cords.y - pos.y) <= hitRadius) || null;
    }

    // The tracked device whose marker is under the cursor (nearest within the
    // icon's radius), or null. Only meaningful while a session is drawing icons;
    // when one device is isolated only it is hittable, so a click elsewhere
    // clears the isolation rather than selecting a hidden marker.
    function hitDeviceAt(pos) {
        if (!pollTrackActive || lastTracks.size === 0) return null;
        const hitRadius = canvas.width * 0.02 + 10; // icon half-size plus slack
        let best = null, bestDist = Infinity;
        lastTracks.forEach((t, entKey) => {
            if (focusedDevice && entKey !== focusedDevice) return;
            const d = Math.hypot(t.x - pos.x, t.y - pos.y);
            if (d <= hitRadius && d < bestDist) { bestDist = d; best = entKey; }
        });
        return best;
    }

    function endReceiverDrag() {
        if (!dragReceiverRef) return;
        dragReceiverRef = null;
        dragOffset = null;
        if (dragMoved) {
            savebuttondiv.appendChild(saveButton);
        }
        dragMoved = false;
    }

    canvas.addEventListener("mousedown", (event) => {
        if (drawToolActive() || dragReceiverRef || panState) return;
        if (!mapReady()) return;
        const pos = zoneMousePos(event);
        const hit = hitReceiverAt(pos);
        if (moveToggle.checked && !pollTrackActive && hit) {
            // Grab offset: the receiver moves with the cursor instead of
            // teleporting its center onto it.
            dragReceiverRef = hit;
            dragOffset = { x: hit.cords.x - pos.x, y: hit.cords.y - pos.y };
            dragMoved = false;
            return;
        }
        panState = {
            startX: event.clientX,
            startY: event.clientY,
            viewX: view.x,
            viewY: view.y,
            moved: false,
        };
        clickCandidate = hit;
        clickDeviceCandidate = hitDeviceAt(pos);
        // Only a click that isn't on a receiver icon can land on a line/pill;
        // hitReceiverAt (endpoints) wins where they overlap.
        clickLinkCandidate = hit ? null : hitRecDistLinkAt(pos);
    });

    canvas.addEventListener("mousemove", (event) => {
        if (dragReceiverRef) {
            if (event.buttons === 0) {
                // The button was released outside the canvas/iframe.
                endReceiverDrag();
                return;
            }
            const pos = zoneMousePos(event);
            dragReceiverRef.cords.x = Math.max(0, Math.min(canvas.width, pos.x + dragOffset.x));
            dragReceiverRef.cords.y = Math.max(0, Math.min(canvas.height, pos.y + dragOffset.y));
            dragMoved = true;
            redrawAll();
            return;
        }
        if (panState) {
            if (event.buttons === 0) {
                panState = null;
                return;
            }
            const rect = canvas.getBoundingClientRect();
            const dx = (event.clientX - panState.startX) * (canvas.width / rect.width);
            const dy = (event.clientY - panState.startY) * (canvas.height / rect.height);
            if (Math.abs(dx) + Math.abs(dy) > 4) panState.moved = true;
            view.x = panState.viewX + dx;
            view.y = panState.viewY + dy;
            clampView();
            redrawAll();
        }
        if (dragReceiverRef || panState) return;
        // Hover reveals the name of the receiver under the cursor (names are
        // hidden by default to avoid overlap). Repaint only when it changes.
        const pos = (drawToolActive() || !mapReady()) ? null : zoneMousePos(event);
        const hit = pos ? hitReceiverAt(pos) : null;
        const next = hit ? hit.entity_id : null;
        // A receiver icon takes priority; otherwise the link under the cursor.
        // Both reveal labels on demand (the receiver's own name; the link's
        // distance pill), so a change in either needs a repaint.
        const overLink = (!next && pos) ? hitRecDistLinkAt(pos) : null;
        let changed = false;
        if (next !== hoveredReceiver) { hoveredReceiver = next; changed = true; }
        if (overLink !== hoveredRecDistLink) { hoveredRecDistLink = overLink; changed = true; }
        if (changed) redrawAll();
        canvas.style.cursor = (next || overLink) ? "pointer" : "";
    });

    canvas.addEventListener("mouseleave", () => {
        // Always drop the cursor: it can be "pointer" from hovering a distance
        // line/pill even when no receiver is hovered (hoveredReceiver null).
        canvas.style.cursor = "";
        if (hoveredReceiver === null && hoveredRecDistLink === null) return;
        hoveredReceiver = null;
        hoveredRecDistLink = null; // hide the hover-revealed distance pill
        redrawAll();
    });

    // Hovering a receiver row in the sidebar list also reveals that receiver's
    // name on the map (same hoveredReceiver state as the map hover). Delegated
    // mouseover/mouseout because the tree is re-rendered; repaint only on change.
    document.addEventListener("mouseover", (event) => {
        const row = event.target.closest('[data-type="focusrec"]');
        if (!row || receiversHidden()) return;
        const id = row.getAttribute("data-id");
        if (id !== hoveredReceiver) {
            hoveredReceiver = id;
            if (mapReady()) redrawAll();
        }
    });
    document.addEventListener("mouseout", (event) => {
        const row = event.target.closest('[data-type="focusrec"]');
        if (!row) return;
        // Leaving a receiver row: clear unless the pointer is entering another row.
        const into = event.relatedTarget && event.relatedTarget.closest
            && event.relatedTarget.closest('[data-type="focusrec"]');
        if (!into && hoveredReceiver !== null) {
            hoveredReceiver = null;
            if (mapReady()) redrawAll();
        }
    });

    document.addEventListener("mouseup", () => {
        endReceiverDrag();
        if (!panState) return;
        const wasClick = !panState.moved;
        panState = null;
        if (!wasClick) return;
        const target = clickCandidate;
        const devTarget = clickDeviceCandidate;
        const linkTarget = clickLinkCandidate;
        clickCandidate = null;
        clickDeviceCandidate = null;
        clickLinkCandidate = null;
        // Clicking a tracker beacon isolates it (only its circles + path + icon
        // show); clicking the same beacon again reverts to all. A beacon click
        // takes priority over the receiver/link/empty-space handling below.
        if (devTarget) {
            focusedDevice = devTarget === focusedDevice ? null : devTarget;
            redrawAll();
            return;
        }
        // Any other plain click reverts beacon isolation ("show all again")...
        let changed = false;
        if (focusedDevice) { focusedDevice = null; changed = true; }
        if (target) {
            // Clicked a receiver: focus it (only it + its links stay); clicking
            // the focused one again clears it. Any single-link highlight clears.
            const next = target.entity_id !== focusedReceiver ? target.entity_id : null;
            if (next !== focusedReceiver) {
                focusedReceiver = next;
                expandGroupForReceiver(next); // reveal the selection in the sidebar
                changed = true;
            }
            if (focusedRecDistLink) { focusedRecDistLink = null; changed = true; }
        } else if (linkTarget) {
            // Clicked a receiver-distance line/pill: isolate that link (only its
            // line + pill stay); clicking it again clears. Receiver focus clears
            // so the two selections never fight over what's shown.
            const nextLink = linkTarget !== focusedRecDistLink ? linkTarget : null;
            if (nextLink !== focusedRecDistLink) { focusedRecDistLink = nextLink; changed = true; }
            if (focusedReceiver) { focusedReceiver = null; changed = true; }
        } else {
            // Empty space: clear both the receiver focus and any link highlight.
            if (focusedReceiver) { focusedReceiver = null; changed = true; }
            if (focusedRecDistLink) { focusedRecDistLink = null; changed = true; }
        }
        if (changed) redrawAll();
    });

    canvas.addEventListener("wheel", (event) => {
        if (!mapReady()) return;
        event.preventDefault();
        // Zoom is allowed while drawing/editing a zone or sub-zone — the polygon
        // overlay is re-rendered below via drawZonePreview so it isn't wiped.
        // The receiver/scale tools stay blocked: their overlays (pending marker,
        // scale line) aren't part of drawZonePreview and a redraw would drop them.
        const zoneDrawActive = drawAreaButton.dataset.active === 'true'
            || drawSubZoneButton.dataset.active === 'true';
        if (drawToolActive() && !zoneDrawActive) return;
        const rect = canvas.getBoundingClientRect();
        const px = (event.clientX - rect.left) * (canvas.width / rect.width);
        const py = (event.clientY - rect.top) * (canvas.height / rect.height);
        const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
        const newZoom = Math.max(1, Math.min(8, view.zoom * factor));
        // Keep the world point under the cursor fixed while zooming.
        view.x = px - ((px - view.x) / view.zoom) * newZoom;
        view.y = py - ((py - view.y) / view.zoom) * newZoom;
        view.zoom = newZoom;
        clampView();
        if (zoneDrawActive) drawZonePreview(); else redrawAll();
    }, { passive: false });

    viewReset.addEventListener("click", () => {
        view.zoom = 1;
        view.x = 0;
        view.y = 0;
        if (!mapReady()) return;
        // Preserve the in-progress polygon overlay when resetting mid-draw.
        const zoneDrawActive = drawAreaButton.dataset.active === 'true'
            || drawSubZoneButton.dataset.active === 'true';
        if (zoneDrawActive) drawZonePreview(); else redrawAll();
    });

    // =================================================================
    // Add data to array
    // =================================================================

    function addDataToFloor(finalcords, floorName, dataType, data) {
        // Check if floor is arratm else initiate it
        if (!Array.isArray(finalcords.floor)) {
            finalcords.floor = [];
        }
        
        let floorExists = finalcords.floor.some(floor => sameFloorName(floor.name, floorName)); // Check if floor exists

        if (!floorExists) {
            // Add floor if it does not exists
            finalcords.floor.push({
            name: floorName,
            scale: null,
            receivers: [],
            zones: []
            });
            console.log(`Added new floor: ${floorName}`);
        } else {
            console.log(`Floor '${floorName}' already exists.`);
        }    
        
        let floor = finalcords.floor.find(floor => sameFloorName(floor.name, floorName)); // Find correct floor

        if (floor) {
            // Control if receiver/zone with the name already exists on the floor
            let enitityExists = null;
            let tmpname = null;
            if(dataType === "receivers"){
                enitityExists = floor[dataType].some(receiver => receiver.entity_id === receiverName);
                tmpname = receiverName;
            }
            if(dataType === "zones"){
                // Allow multiple zones with the same display name.
                enitityExists = false;
                tmpname = zoneName;
            }
            if(dataType === "scale"){
                floor.scale = data;
                savebuttondiv.appendChild(saveButton);
                return true;
            }

            if (!enitityExists) {
                // Add new receiver if it does not exist
                floor[dataType].push(data);
                savebuttondiv.appendChild(saveButton);
                return true;
              } else {
                console.log(`'${dataType}' with the name '${tmpname}' already exists on ${floorName}.`);
                bpsToast(`'${dataType}' with the name '${tmpname}' already exists on ${floorName}.`);
                buttonreset();
                clearCanvas();
                drawElements();
                return false;
              }
        } else {
            console.log(`Floor with name '${floorName}' not found.`);
            return false;
        }
      }

    // =================================================================
    // Draw elements on canvas
    // =================================================================

    function scaleStatus(value){
        if(value == null){
            document.getElementById("scalenok").style.display = "flex";
            document.getElementById("scaleok").style.display = "none";
        } else {
            document.getElementById("scalenok").style.display = "none";
            document.getElementById("scaleok").style.display = "flex";
        }
    }

    // Text with a light halo, horizontally centered on cx and clamped to the
    // canvas so labels stay fully readable at the edges.
    function drawCenteredLabel(text, cx, baselineY, font, color) {
        if (!text) return;
        ctx.font = font;
        const width = ctx.measureText(text).width;
        let lx = cx - width / 2;
        lx = Math.max(4, Math.min(canvas.width - width - 4, lx));
        ctx.lineJoin = "round";
        ctx.lineWidth = 5;
        ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
        ctx.strokeText(text, lx, baselineY);
        ctx.fillStyle = color;
        ctx.fillText(text, lx, baselineY);
    }

    function drawElements(xp, yp, type){
        const tmpdrawcords = [];
        const iconSize = mapIconSize(); // zoom-compensated while tracking (see mapIconSize)
        deleteButton.remove();
        drawGrid();

        // Only a placement click (placeReceiver passes world coordinates) may
        // update the pending receiver coordinates; plain redraws (grid
        // toggle, sidebar deletes) must not clobber them.
        if (xp !== undefined && yp !== undefined) {
            tmpcords = { x: xp, y: yp };
        }
        // Keep the pending (unsaved) receiver marker visible across repaints
        // while Place Receiver mode is active.
        if (addDeviceButton.dataset.active === 'true' && tmpcords
            && Number.isFinite(tmpcords.x) && Number.isFinite(tmpcords.y)) {
            tmpdrawcords.push({
                entity_id: receiverName,
                type: "receiver",
                cords: tmpcords,
            });
        }

        let floor = finalcords.floor.find(floor => sameFloorName(floor.name, SelMapName)); //Add all existing

        // A focused receiver that no longer exists releases the focus.
        if (focusedReceiver && !(floor && (floor.receivers || []).some(r => r.entity_id === focusedReceiver))) {
            focusedReceiver = null;
        }

        if (floor) {
            myScaleVal = floor.scale; // Get the scalevalue for the floor
            scaleStatus(myScaleVal)//Show or hide status for scale value
            // Delete Floor lives in the Tools grid, right after Clear Canvas, so
            // the two sit side by side on the bottom row.
            mapbuttondiv.appendChild(deleteButton);

            if (floor.receivers.length < 3) {
                trackdiv.style.display = "none";
            } else {
                trackdiv.style.display = "";
            }

            // Loopa through all receivers in floor
            floor.receivers.forEach((receiver, index) => {
                receiver.type = "receiver";
                tmpdrawcords.push(receiver);
            });
            // Loopa through all zones in floor
            floor.zones.forEach((zone, index) => {
                if (!zone.zone_id) {
                    zone.zone_id = createZoneId();
                }
                zone.type = "zone";
                tmpdrawcords.push(zone);
            });
            // Sub-zones are pushed after zones so they paint on top of them.
            (floor.subzones || []).forEach(sub => {
                if (!sub.sub_zone_id) {
                    sub.sub_zone_id = createSubZoneId();
                }
                sub.type = "subzone";
                tmpdrawcords.push(sub);
            });
        } else {
            // No saved floor matches the selection: tracking has nothing to
            // iterate, so do not offer it.
            trackdiv.style.display = "none";
        }

        // Each zone's display colour (manual or unique auto), keyed by zone_id
        // and shared with the sidebar. Zone name pills are collected here and
        // drawn AFTER the loop so they sit above sub-zones (which paint on top
        // of their parent zone).
        const zoneColorById = new Map();
        ((floor && floor.zones) || []).forEach((z, i) => {
            zoneColorById.set(z.zone_id, z.uncolored ? null : zoneDisplayColor(z, i));
        });
        const zonePills = [];
        const zoneStrokes = []; // black edges, drawn after sub-zones so zone lines sit on top
        const subPills = [];

        tmpdrawcords.forEach((item, index) => {

            if (item.type == "receiver"){
                // Skip receivers while laying out geometry so the outlines being
                // worked on stay uncluttered. Same predicate as hit-testing, so a
                // receiver is clickable exactly when it is drawn.
                if (receiversHidden()) return;
                if (focusedReceiver && item.entity_id !== focusedReceiver) return;
                const x = item.cords.x;
                const y = item.cords.y;
                const recOffline = isReceiverOffline(item.entity_id);
                drawReceiverIcon(x, y, iconSize, recOffline);

                // Names are hidden by default (too many receivers overlap);
                // show one only when it's hovered or focused. The full list of
                // names lives in the Zones & Receivers sidebar.
                if (item.entity_id === hoveredReceiver || item.entity_id === focusedReceiver) {
                    // Name centered above the icon; below it when too close to
                    // the top edge.
                    let labelY = y - iconSize / 2 - 8;
                    if (labelY < 24) {
                        labelY = y + iconSize / 2 + 24;
                    }
                    drawCenteredLabel((recOffline ? "(Offline) " : "") + item.entity_id, x, labelY,
                        "600 22px system-ui, sans-serif", recOffline ? OFFLINE_RED : "#111111");
                }
            }
            if (item.type == "zone"){
                const pts = zonePerimeterPoints(item);
                if (pts.length < 3) return;
                const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
                const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
                if (item.no_go) {
                    // Dead space (issue #60): grey hatching instead of a room
                    // tint. Deferred edge is drawn dashed-grey below.
                    drawHatchedZone(pts);
                    zoneStrokes.push({ pts, noGo: true });
                    zonePills.push({ text: item.entity_id, cx, cy, color: "#bdbdbd" });
                    return;
                }
                // null => the zone's colour was removed: no tint, neutral pill.
                const zoneColor = zoneColorById.has(item.zone_id) ? zoneColorById.get(item.zone_id) : zoneDisplayColor(item, 0);

                if (zoneColor) {
                    // Unique tint so each room reads as its own area.
                    tracePolygon(pts);
                    ctx.save();
                    ctx.globalAlpha = 0.20;
                    ctx.fillStyle = zoneColor;
                    ctx.fill();
                    ctx.restore();
                }
                // Defer the black edge + the name pill so both draw ABOVE sub-zones
                // (zone lines on top of sub-zone lines; name readable over all).
                zoneStrokes.push({ pts });
                zonePills.push({ text: item.entity_id, cx, cy, color: zoneColor || "#e8e8e8" });
            }
            if (item.type == "subzone"){
                const pts = item.cords || [];
                if (pts.length < 3) return;
                // Contrasting colour of the parent zone (or own vibrant hue if the
                // parent is uncoloured); see subZoneRenderColor. Clip to the parent
                // zone so the sub-zone stays inside the zone's edges even when it
                // runs edge to edge.
                const sc = subZoneRenderColor(item, floor);
                const subColor = sc.color;
                const parent = (floor.zones || []).find(z => (z.zone_id || z.entity_id) === item.parent);
                const parentPts = parent ? zonePerimeterPoints(parent) : null;
                ctx.save();
                if (parentPts && parentPts.length >= 3) {
                    tracePolygon(parentPts);
                    ctx.clip();
                }
                tracePolygon(pts);
                ctx.globalAlpha = sc.alpha;
                ctx.fillStyle = subColor;
                ctx.fill();
                ctx.globalAlpha = 1;
                ctx.strokeStyle = subColor;
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.restore();

                const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
                const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
                subPills.push({ text: item.entity_id, cx, cy, color: subColor });
            }
        });

        // Zone black edges next — above sub-zone fills/lines, so where a sub-zone
        // meets the zone boundary the crisp black zone line is what shows.
        zoneStrokes.forEach(z => {
            tracePolygon(z.pts);
            if (z.noGo) {
                // Dashed grey edge so a no-go zone never reads as a normal room.
                ctx.save();
                ctx.strokeStyle = "#616161";
                ctx.lineWidth = 2;
                ctx.setLineDash([12, 8]);
                ctx.stroke();
                ctx.restore();
            } else {
                ctx.strokeStyle = "#000000";
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        });
        // Name pills on top: sub-zones, then zones (a room name stays readable).
        subPills.forEach(s => drawColorPill(s.text, s.cx, s.cy, s.color, "#000000", 16));
        zonePills.forEach(z => drawColorPill(z.text, z.cx, z.cy, z.color, "#000000", 20));

        drawReceiverDistances();
        drawAdjustGhost();
        renderEntityTree(floor);
        renderScannerIssues();
        renderScannerLinkingSidebar(); // re-scope the "not reporting" heads-up to this floor (cached data, no refetch)

        // Keep the map's Save/Cancel actions in sync with tool state. Every
        // activation and every exit path routes through drawElements, so this
        // single point shows them exactly while a layout tool is active.
        if (mapToolActions) mapToolActions.style.display = anyLayoutToolActive() ? '' : 'none';
    }

    // While an adjust preview is active, overlay the proposed shapes for the
    // set being adjusted (zones OR sub-zones) as a green dashed outline on top
    // of the current ones. finalcords stays untouched until Apply.
    function drawAdjustGhost() {
        if (!adjustPreview) return;
        const isSub = adjustPreview.target === 'subzones';
        const list = isSub ? adjustPreview.subzones : adjustPreview.zones;
        ctx.save();
        ctx.setLineDash(isSub ? [4, 5] : [10, 8]);
        ctx.lineWidth = isSub ? 2 : 3;
        ctx.strokeStyle = "#1b7f3b";
        for (const z of (list || [])) {
            const pts = z.cords || [];
            if (pts.length < 3) continue;
            ctx.beginPath();
            ctx.moveTo(pts[0].x, pts[0].y);
            for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
            ctx.closePath();
            ctx.stroke();
        }
        ctx.restore();
    }

    // The stable hardware token of a scanner slug (trailing hex group Bermuda
    // derives from the MAC), mirroring the backend's _scanner_token. Stored on a
    // placement when it's re-linked so future renames stay detectable.
    function scannerTokenJs(slug) {
        if (!slug) return null;
        const last = String(slug).split("_").pop().toLowerCase();
        return /^[0-9a-f]{5,12}$/.test(last) ? last : null;
    }

    // Naming-mismatch warnings (issue #64). "Unmatched" is recomputed live from
    // finalcords + the known scanner slugs so a re-link/remove clears it at once;
    // the re-link suggestion comes from the backend diagnostics.
    function renderScannerIssues() {
        const host = document.getElementById("scannerissues");
        if (!host) return;
        const known = new Set(receiverOptions);
        const placed = new Set();
        (finalcords.floor || []).forEach(f => (f.receivers || []).forEach(r => { if (r && r.entity_id) placed.add(r.entity_id); }));
        const suggestOf = {};
        (scannerDiagnostics.unmatched_receivers || []).forEach(u => { suggestOf[u.entity_id] = u.suggested; });

        const unmatched = [];
        // Only flag once the scanner list has actually loaded (mirrors isReceiverOffline).
        if (known.size) {
            (finalcords.floor || []).forEach(f => (f.receivers || []).forEach(r => {
                if (r && r.entity_id && !known.has(r.entity_id)) {
                    unmatched.push({ entity_id: r.entity_id, floor: f.name, suggested: suggestOf[r.entity_id] || null });
                }
            }));
        }
        const unplaced = (scannerDiagnostics.unplaced_scanners || []).filter(s => !placed.has(s));

        if (!unmatched.length && !unplaced.length) { host.innerHTML = ""; return; }
        let html = '<div class="bps-scanner-issues"><div class="bps-issues-title">Scanner issues</div>';
        unmatched.forEach(u => {
            html += '<div class="bps-issue">'
                + `<span class="bps-issue-msg" title="${escHtml(u.entity_id)}">No Bermuda sensor for “${escHtml(u.entity_id)}”${u.floor ? " ("+escHtml(u.floor)+")" : ""}</span>`;
            if (u.suggested) {
                html += `<button class="bps-btn bps-btn-outline bps-relink-btn" data-type="relinkrec" data-id="${escHtml(u.entity_id)}" data-target="${escHtml(u.suggested)}" title="Rename this placement to the live scanner ${escHtml(u.suggested)}">Re-link → ${escHtml(u.suggested)}</button>`;
            } else {
                html += '<span class="bps-issue-hint">no match — remove or re-place</span>';
            }
            html += '</div>';
        });
        if (unplaced.length) {
            html += `<div class="bps-issue-note">Reporting a distance but not placed: ${unplaced.map(escHtml).join(", ")}</div>`;
        }
        html += '</div>';
        host.innerHTML = html;
    }

    // Distance-sensor states that mean "no reading right now" (mirrors the
    // backend's _NO_DISTANCE_STATES).
    function linkingHasReading(state) {
        return state !== null && state !== "" && state !== "unknown" && state !== "unavailable";
    }

    // Fetch a fresh linking snapshot, then repaint both consumers: the compact
    // "not reporting" heads-up in the map sidebar and the full Debugging tab.
    // Live HA state changes constantly, so there's no useful cache to keep — a
    // stale/failed fetch just shows an empty snapshot.
    async function loadScannerLinking() {
        scannerLinkingLoading = true;
        renderDebugView();
        let data = { placed: [], unplaced: [], beacons: [] };
        try {
            const res = await bpsFetch('/api/bps/scanner_linking');
            if (res.ok) {
                const parsed = await res.json();
                if (parsed && typeof parsed === 'object') {
                    data = {
                        placed: Array.isArray(parsed.placed) ? parsed.placed : [],
                        unplaced: Array.isArray(parsed.unplaced) ? parsed.unplaced : [],
                        beacons: Array.isArray(parsed.beacons) ? parsed.beacons : [],
                    };
                }
            }
        } catch (e) { /* transient; show an empty snapshot */ }
        scannerLinkingData = data;
        scannerLinkingLoading = false;
        renderScannerLinkingSidebar();
        renderDebugView();
    }

    const LINKING_STATUS_LABEL = { live: "Live", silent: "No reading", unmatched: "Unmatched" };
    const LINKING_STATUS_RANK = { unmatched: 0, silent: 1, live: 2 };
    const linkingStatusOf = r => (LINKING_STATUS_RANK.hasOwnProperty(r && r.status) ? r.status : "unmatched");

    // Map-view sidebar: a compact heads-up listing only placed receivers on the
    // CURRENT floor that are linked but silent (no distance right now), names
    // only. The full per-entity picture lives in the Debugging tab. Hidden
    // entirely when nothing on this floor is silent. Uses the cached snapshot,
    // so it's re-scoped to the viewed floor on each drawElements without a
    // refetch.
    function renderScannerLinkingSidebar() {
        const host = document.getElementById("scannerlinking");
        if (!host) return;
        const data = scannerLinkingData;
        if (!data) { host.innerHTML = ""; return; }
        const silent = (data.placed || []).filter(r =>
            linkingStatusOf(r) === "silent" && (!SelMapName || sameFloorName(r.floor, SelMapName)));
        if (!silent.length) { host.innerHTML = ""; return; }
        silent.sort((a, b) => String(a.entity_id).localeCompare(String(b.entity_id)));
        host.innerHTML = '<div class="bps-linking-mini">'
            + '<div class="bps-linking-mini-title">Not reporting right now</div>'
            + '<ul class="bps-linking-mini-list">'
            + silent.map(r => '<li title="' + escHtml(r.entity_id) + '">' + escHtml(r.entity_id) + '</li>').join("")
            + '</ul>'
            + '<div class="bps-linking-mini-hint">Linked, but no distance right now. See the <strong>Debugging</strong> tab for details.</div>'
            + '</div>';
    }

    // Debugging tab: the complete receiver-linking picture, laid out as a table
    // for easy visual scanning — every placed receiver, its status, and the
    // per-device Bermuda distance sensors feeding it with their live states.
    // Receivers sub-view: every placed receiver, its status, and the per-device
    // Bermuda sensors feeding it. Returns an HTML string.
    function debugReceiversHtml(data) {
        const rows = (data.placed || []).slice().sort((a, b) =>
            (LINKING_STATUS_RANK[linkingStatusOf(a)] - LINKING_STATUS_RANK[linkingStatusOf(b)])
            || String(a.floor || "").localeCompare(String(b.floor || ""))
            || String(a.entity_id).localeCompare(String(b.entity_id)));
        const counts = { live: 0, silent: 0, unmatched: 0 };
        rows.forEach(r => { counts[linkingStatusOf(r)]++; });

        let html = '<div class="bps-debug-summary">'
            + '<span class="bps-linking-chip bps-chip-live">' + counts.live + ' Live</span>'
            + '<span class="bps-linking-chip bps-chip-silent">' + counts.silent + ' No reading</span>'
            + '<span class="bps-linking-chip bps-chip-unmatched">' + counts.unmatched + ' Unmatched</span>'
            + '</div>';

        if (!rows.length) {
            html += '<p class="bps-debug-msg">No receivers placed yet. Place receivers on the Map &amp; Setup tab.</p>';
        } else {
            html += '<div class="bps-debug-tablewrap"><table class="bps-debug-table"><thead><tr>'
                + '<th>Receiver</th><th>Floor</th><th>Status</th><th>Hardware</th><th>Bermuda distance sensors (device: reading)</th>'
                + '</tr></thead><tbody>';
            rows.forEach(r => {
                const status = linkingStatusOf(r);
                let cell;
                if (status === "unmatched") {
                    cell = '<span class="bps-debug-none">No distance sensor carries this name</span>';
                } else if (!(r.sensors || []).length) {
                    cell = '<span class="bps-debug-none">no sensors</span>';
                } else {
                    cell = '<div class="bps-debug-readings">' + r.sensors.map(s => {
                        // Three states, worst to mildest: a real reading (live, green);
                        // "unavailable" — the entity/scanner is actually gone (bright
                        // orange-red, a real problem); "unknown"/empty — a matching
                        // sensor with no value yet (amber, usually just no BLE contact).
                        const st = (s.state === null || s.state === undefined) ? "" : String(s.state);
                        let cls, val;
                        if (linkingHasReading(s.state)) { cls = "is-live"; val = st; }
                        else if (st.toLowerCase() === "unavailable") { cls = "is-unavailable"; val = st; }
                        else { cls = "is-silent"; val = st === "" ? "—" : st; }
                        return '<span class="bps-debug-reading ' + cls + '" title="' + escHtml(s.entity_id) + '">'
                            + '<span class="bps-debug-dev">' + escHtml(s.device) + '</span>'
                            + '<span class="bps-debug-val">' + escHtml(val) + '</span></span>';
                    }).join("") + '</div>';
                }
                html += '<tr class="bps-debug-row bps-status-' + status + '">'
                    + '<td class="bps-debug-name" title="' + escHtml(r.entity_id) + '">' + escHtml(r.entity_id) + '</td>'
                    + '<td>' + (r.floor ? escHtml(r.floor) : "—") + '</td>'
                    + '<td><span class="bps-linking-chip bps-chip-' + status + '">' + LINKING_STATUS_LABEL[status] + '</span></td>'
                    + '<td class="bps-debug-hw">' + (r.token ? escHtml(r.token) : "—") + '</td>'
                    + '<td>' + cell + '</td>'
                    + '</tr>';
            });
            html += '</tbody></table></div>';
        }

        const unplaced = (data.unplaced || []).slice().sort((a, b) => String(a.entity_id).localeCompare(String(b.entity_id)));
        if (unplaced.length) {
            html += '<h4 class="bps-debug-subtitle">Scanners with distance sensors but not placed on any floor</h4>'
                + '<div class="bps-debug-tablewrap"><table class="bps-debug-table"><thead><tr>'
                + '<th>Scanner</th><th>Hardware</th><th>Sensors</th><th>Reporting</th></tr></thead><tbody>';
            unplaced.forEach(u => {
                html += '<tr>'
                    + '<td class="bps-debug-name" title="' + escHtml(u.entity_id) + '">' + escHtml(u.entity_id) + '</td>'
                    + '<td class="bps-debug-hw">' + (u.token ? escHtml(u.token) : "—") + '</td>'
                    + '<td>' + (u.sensor_count || 0) + '</td>'
                    + '<td>' + (u.reporting_count || 0) + '</td>'
                    + '</tr>';
            });
            html += '</tbody></table></div>';
        }

        html += '<p class="bps-debug-help"><strong>No reading</strong> = the name matches a Bermuda distance sensor but it has no value right now — usually just no recent BLE contact, not a naming problem. '
            + '<strong>Unmatched</strong> = no distance sensor carries that name at all; fix it with the <em>Re-link</em> button in the Map view’s “Scanner issues” panel, or rename the entity in Bermuda.</p>';
        return html;
    }

    // Beacons sub-view: per tracked device, the receivers currently detecting
    // it, closest first (the inverse of the receivers view). Same table layout
    // as the receivers view — summary chips, header row, one row per beacon —
    // so the two read alike. Returns an HTML string.
    function debugBeaconsHtml(data) {
        const beacons = (data.beacons || []).slice().sort((a, b) => {
            // Undetected beacons first (the anomaly worth seeing), then by name —
            // mirrors the receivers view surfacing its problem rows at the top.
            const ad = (a.receivers || []).length ? 1 : 0;
            const bd = (b.receivers || []).length ? 1 : 0;
            return (ad - bd) || String(a.device || "").localeCompare(String(b.device || ""));
        });
        const detected = beacons.filter(b => (b.receivers || []).length).length;
        const undetected = beacons.length - detected;

        let html = '<div class="bps-debug-summary">'
            + '<span class="bps-linking-chip bps-chip-live">' + detected + ' Detected</span>'
            + '<span class="bps-linking-chip bps-chip-silent">' + undetected + ' Not detected</span>'
            + '</div>';

        if (!beacons.length) {
            html += '<p class="bps-debug-msg">No beacons yet — tracked devices appear here once Bermuda reports a distance to them.</p>';
            return html;
        }

        html += '<div class="bps-debug-tablewrap"><table class="bps-debug-table"><thead><tr>'
            + '<th>Beacon</th><th>Status</th><th>Receivers</th><th>Receivers detecting it (closest first)</th>'
            + '</tr></thead><tbody>';
        beacons.forEach(b => {
            const recs = b.receivers || [];
            const isDetected = recs.length > 0;
            const status = isDetected ? "live" : "silent";
            let cell;
            if (!isDetected) {
                cell = '<span class="bps-debug-none">No receiver currently detects this beacon.</span>';
            } else {
                // Each receiver has a current distance, so every pill is a live (green)
                // reading. The backend already sorts them closest first; keep that
                // order left-to-right, matching the receivers view's pill cell.
                cell = '<div class="bps-debug-readings">' + recs.map(r =>
                    '<span class="bps-debug-reading is-live" title="' + escHtml(r.scanner) + '">'
                    + '<span class="bps-debug-dev">' + escHtml(r.scanner) + '</span>'
                    + '<span class="bps-debug-val">' + escHtml(String(r.distance)) + ' ' + escHtml(r.unit || 'm') + '</span></span>'
                ).join("") + '</div>';
            }
            html += '<tr class="bps-debug-row bps-status-' + status + '">'
                + '<td class="bps-debug-name" title="' + escHtml(b.device) + '">' + escHtml(b.device) + '</td>'
                + '<td><span class="bps-linking-chip bps-chip-' + status + '">' + (isDetected ? "Detected" : "None") + '</span></td>'
                + '<td>' + recs.length + '</td>'
                + '<td>' + cell + '</td>'
                + '</tr>';
        });
        html += '</tbody></table></div>';
        html += '<p class="bps-debug-help">Each row is a tracked device (beacon) and the receivers reporting a live distance to it right now, closest first. '
            + '<strong>None</strong> = no receiver currently has a reading for it, usually because the device is off or out of range.</p>';
        return html;
    }

    function renderDebugView() {
        const host = document.getElementById("debuglinking");
        if (!host) return;
        if (scannerLinkingLoading && !scannerLinkingData) { host.innerHTML = '<p class="bps-debug-msg">Loading…</p>'; return; }
        const data = scannerLinkingData;
        if (!data) { host.innerHTML = '<p class="bps-debug-msg">No data yet. <button type="button" class="bps-btn bps-btn-outline" data-type="refreshlinking">Refresh</button></p>'; return; }

        // Two sub-tabs so each view is short: Receivers (per scanner) and
        // Beacons (per tracked device). Refresh is shared (one snapshot feeds both).
        const sub = debugSubtab === "beacons" ? "beacons" : "receivers";
        let html = '<div class="bps-debug-toolbar">'
            + '<div class="bps-subtabs">'
            + '<button type="button" class="bps-subtab' + (sub === "receivers" ? " active" : "") + '" data-type="debugsubtab" data-tab="receivers">Receivers</button>'
            + '<button type="button" class="bps-subtab' + (sub === "beacons" ? " active" : "") + '" data-type="debugsubtab" data-tab="beacons">Beacons</button>'
            + '</div>'
            + '<button type="button" class="bps-btn bps-btn-outline" data-type="refreshlinking">Refresh</button>'
            + '</div>';
        html += (sub === "beacons") ? debugBeaconsHtml(data) : debugReceiversHtml(data);
        host.innerHTML = html;
    }

    // Sidebar: one section per zone with the receivers placed inside it.
    function renderEntityTree(floor) {
        const tree = document.getElementById("entitytree");
        // Header "Colours" toggle: shown only when the floor has zones; label
        // reflects whether any zone is currently coloured.
        if (zoneColorsToggle) {
            const zs = (floor && floor.zones) || [];
            if (zs.length) {
                const anyColored = zs.some(z => !z.uncolored);
                zoneColorsToggle.style.display = "";
                zoneColorsToggle.textContent = anyColored ? "Colours: on" : "Colours: off";
            } else {
                zoneColorsToggle.style.display = "none";
            }
        }
        // A zone colour swatch is focused right now — its native colour picker
        // is likely open. Rebuilding the tree would replace that <input> and
        // slam the picker shut (it "appears and disappears"), so leave the tree
        // DOM intact this pass; a later render (after focus leaves the swatch)
        // refreshes it. The canvas still redraws around this.
        const active = document.activeElement;
        if (tree && active && active.classList && active.classList.contains("bps-zone-swatch") && tree.contains(active)) {
            return;
        }
        if (!floor) {
            tree.innerHTML = '<p class="bps-empty">Select a floor to see its zones and receivers.</p>';
            return;
        }
        const trashSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>';
        const pencilSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>';
        // Vertical double-arrow: the receiver mount-height editor.
        const rulerSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"></path><path d="M8 7l4-4 4 4"></path><path d="M8 17l4 4 4-4"></path></svg>';
        const chevronSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg>';
        // Toggle a zone's colour on/off: filled drop = add, slashed circle = remove.
        const colorOnSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="currentColor"></circle></svg>';
        const colorOffSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8"></circle><line x1="6" y1="18" x2="18" y2="6"></line></svg>';
        // No-entry sign: toggle a zone as no-go dead space (issue #60).
        // Hatched square — mirrors the grey diagonal hatching a no-go zone gets
        // on the map, and is unmistakably different from the colour-toggle's
        // slashed circle (they used to be two near-identical circles).
        const noGoSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"></rect><line x1="3" y1="14" x2="14" y2="3"></line><line x1="9" y1="21" x2="21" y2="9"></line></svg>';
        // Stable per-floor suffix so the two synthetic groups ("No zone" /
        // "Unlinked sub-zones") collapse independently on each floor, like real
        // zones do (those get globally-unique zone ids). Floor names don't churn,
        // so these keys stay stable and don't accumulate.
        const floorKey = floor.name || "";
        // Header for a collapsible zone group. `key` identifies the group in
        // expandedZones (groups are collapsed by default, so a key absent from
        // the set renders collapsed); `countHtml` is the "· N" badge (kept out of
        // the ellipsis-clipped title so it stays visible); `actionsHtml` is the
        // optional edit/remove button block.
        const groupOpen = (key, titleHtml, countHtml, actionsHtml, headBg) => {
            const collapsed = !expandedZones.has(key);
            // Overlay the zone's accent on its header (over the default accent).
            // A solid colour is wrapped into a flat translucent layer; a value
            // that is already an image/gradient (the no-go hatch) is layered
            // as-is — nesting a gradient inside linear-gradient() is invalid CSS
            // and the whole declaration would be dropped.
            let headStyle = '';
            if (headBg) {
                const layer = /gradient\(/.test(headBg) ? headBg : `linear-gradient(${headBg}, ${headBg})`;
                headStyle = ` style="background: ${layer}, hsl(var(--sidebar-accent))"`;
            }
            return '<div class="bps-zone-group' + (collapsed ? ' bps-collapsed' : '') + '">'
                + `<div class="bps-zone-head" data-type="togglezone" data-key="${escHtml(key)}"${headStyle}>`
                + `<span class="bps-caret">${chevronSvg}</span>`
                + `<span class="bps-zone-title">${titleHtml}</span>`
                + (countHtml || '')
                + (actionsHtml || '')
                + '</div>';
        };
        const subzones = (floor.subzones || []);
        const subRow = s => {
            const sid = s.sub_zone_id || s.entity_id;
            const dot = subZoneRenderColor(s, floor).color; // effective (contrast) colour, matches the map
            return `<li class="bps-subzone-row"><span class="bps-subzone-dot" style="background:${escHtml(dot)}"></span>`
                + `<span title="${escHtml(s.entity_id)}">${escHtml(s.entity_id)}</span>`
                + `<button class="bps-icon-btn" title="Edit sub-zone" data-type="editsubzone" data-id="${escHtml(sid)}">${pencilSvg}</button>`
                + `<button class="bps-icon-btn" title="Remove sub-zone" data-type="removesubzone" data-id="${escHtml(sid)}">${trashSvg}</button></li>`;
        };
        const receiverRow = r => {
            const off = isReceiverOffline(r.entity_id);
            const label = (off ? "(Offline) " : "") + r.entity_id;
            // The whole row focuses that receiver on the map (only it and its
            // circle stay visible), mirroring a click on its icon. The trash
            // button's handler runs first, so removing never focuses.
            const cls = "bps-rec-row" + (r.entity_id === focusedReceiver ? " bps-rec-focused" : "");
            // Mount height badge + editor. The ruler button prompts for the
            // height (m above this floor); the badge shows the current value.
            const hBadge = Number.isFinite(r.height)
                ? `<span class="bps-rec-height" title="Mount height above this floor">${escHtml(String(r.height))} m</span>` : "";
            // Badge + buttons live in an actions group (like zone rows) so the
            // height and delete buttons sit in a fixed right-hand column, no
            // matter the receiver name's length or whether a badge is shown.
            return `<li class="${cls}" data-type="focusrec" data-id="${escHtml(r.entity_id)}">`
                + `<span title="${escHtml(r.entity_id)}"${off ? ' style="color:#d32f2f"' : ''}>${escHtml(label)}</span>`
                + `<span class="bps-zone-actions">`
                + hBadge
                + `<button class="bps-icon-btn" title="Set mount height (m)" data-type="recheight" data-id="${escHtml(r.entity_id)}">${rulerSvg}</button>`
                + `<button class="bps-icon-btn" title="Remove receiver" data-type="removerec" data-id="${escHtml(r.entity_id)}">${trashSvg}</button>`
                + `</span></li>`;
        };

        const receivers = (floor.receivers || []).filter(r => r && r.entity_id && r.cords);
        const claimed = new Set();
        let html = "";
        (floor.zones || []).forEach((zone, zi) => {
            const pts = zonePerimeterPoints(zone);
            const inside = pts.length >= 3
                ? receivers.filter(r => !claimed.has(r.entity_id) && pointInPolygon(r.cords.x, r.cords.y, pts))
                : [];
            inside.forEach(r => claimed.add(r.entity_id));
            const zoneDomId = zone.zone_id || zone.entity_id;
            const subs = subzones.filter(s => s.parent === zoneDomId);
            const zoneColor = zoneDisplayColor(zone, zi);
            const uncolored = !!zone.uncolored;
            const noGo = !!zone.no_go;
            const zoneActions = '<span class="bps-zone-actions">'
                + `<input type="color" class="bps-zone-swatch${uncolored ? ' bps-swatch-off' : ''}" data-type="zonecolor" data-id="${escHtml(zoneDomId)}" value="${colorToHex(zoneColor)}" title="Pick zone colour">`
                + `<button class="bps-icon-btn" title="${uncolored ? 'Add colour' : 'Remove colour'}" data-type="zonetogglecolor" data-id="${escHtml(zoneDomId)}">${uncolored ? colorOnSvg : colorOffSvg}</button>`
                + `<button class="bps-icon-btn bps-nogo-btn${noGo ? ' bps-nogo-on' : ''}" title="${noGo ? 'Unmark no-go zone' : 'Mark as no-go (dead space — nothing can be here)'}" data-type="zonetogglenogo" data-id="${escHtml(zoneDomId)}">${noGoSvg}</button>`
                + `<button class="bps-icon-btn" title="Edit zone" data-type="editzone" data-id="${escHtml(zoneDomId)}">${pencilSvg}</button>`
                + `<button class="bps-icon-btn" title="Remove zone" data-type="removezone" data-id="${escHtml(zoneDomId)}">${trashSvg}</button>`
                + '</span>';
            // A no-go zone's header wears a grey hatched accent instead of its
            // room colour, matching the map (issue #60).
            const headBg = noGo
                ? "repeating-linear-gradient(45deg, hsla(0,0%,45%,0.28) 0 6px, transparent 6px 12px)"
                : (uncolored ? "" : colorToTranslucent(zoneColor, 0.35));
            html += groupOpen(zoneDomId,
                `<span title="${escHtml(zone.entity_id)}">${escHtml(zone.entity_id)}${noGo ? ' <span class="bps-nogo-tag">no-go</span>' : ''}</span>`,
                `<span class="bps-count"> · ${inside.length}</span>`,
                zoneActions,
                headBg);
            if (inside.length) {
                html += "<ul>" + inside.map(receiverRow).join("") + "</ul>";
            }
            if (subs.length) {
                html += '<ul class="bps-subzone-list">' + subs.map(subRow).join("") + "</ul>";
            }
            html += "</div>";
        });
        // Sub-zones whose parent zone no longer exists — still listed so they
        // can be edited or deleted.
        const zoneIds = new Set((floor.zones || []).map(z => z.zone_id || z.entity_id));
        const orphanSubs = subzones.filter(s => !zoneIds.has(s.parent));
        if (orphanSubs.length) {
            html += groupOpen(`__orphan_subs__::${floorKey}`, "Unlinked sub-zones",
                `<span class="bps-count"> · ${orphanSubs.length}</span>`)
                + '<ul class="bps-subzone-list">' + orphanSubs.map(subRow).join("") + "</ul></div>";
        }
        const unzoned = receivers.filter(r => !claimed.has(r.entity_id));
        if (unzoned.length) {
            html += groupOpen(`__unzoned__::${floorKey}`, "No zone",
                `<span class="bps-count"> · ${unzoned.length}</span>`)
                + "<ul>" + unzoned.map(receiverRow).join("") + "</ul></div>";
        }
        tree.innerHTML = html || '<p class="bps-empty">No zones or receivers on this floor yet.</p>';
    }

    // =================================================================
    // Trilateration distance circles toggle
    // =================================================================

    const circleToggle = document.getElementById("circleToggle");
    circleToggle.checked = localStorage.getItem("bpsCircles") === "on"; // off by default
    circleToggle.addEventListener("change", () => {
        localStorage.setItem("bpsCircles", circleToggle.checked ? "on" : "off");
        // The toggle is only shown while tracking, so redraw the tracking view
        // (circles + receiver tints) immediately instead of waiting for the next
        // poll tick. redrawAll is a no-op-safe full repaint.
        if (img.naturalWidth > 0) redrawAll();
    });

    // Trace-path toggle: same lifecycle as the circles toggle (revealed only
    // while tracking, persisted, off by default).
    const traceToggle = document.getElementById("traceToggle");
    traceToggle.checked = localStorage.getItem("bpsTracePath") === "on"; // off by default
    traceToggle.addEventListener("change", () => {
        localStorage.setItem("bpsTracePath", traceToggle.checked ? "on" : "off");
        if (img.naturalWidth > 0) redrawAll();
    });

    // Receiver-distances toggle: needs no tracking session (it compares the
    // latest calibration solve against the map), so it is always visible.
    // Switching it on re-polls calibration for the freshest matrix; the
    // overlay repaints when that lands (see pollCalibration).
    const recDistToggle = document.getElementById("recDistToggle");
    const recDistLegend = document.getElementById("recDistLegend"); // colour key overlay
    recDistToggle.checked = localStorage.getItem("bpsRecDist") === "on"; // off by default
    // How many of each receiver's closest links to draw (0 = all). Only shown
    // while the overlay is on — it has nothing to configure otherwise.
    const recDistCount = document.getElementById("recDistCount");
    recDistCount.value = localStorage.getItem("bpsRecDistCount") || "0";
    if (![...recDistCount.options].some(o => o.value === recDistCount.value)) recDistCount.value = "0";
    // Filter links by calibration colour (all | green | blue | red | offcolour).
    const recDistColor = document.getElementById("recDistColor");
    recDistColor.value = localStorage.getItem("bpsRecDistColor") || "all";
    if (![...recDistColor.options].some(o => o.value === recDistColor.value)) recDistColor.value = "all";
    // Which detected distance the pills show and the colour is judged on
    // (calibrated | raw). Default calibrated — the post-correction residual.
    const recDistMode = document.getElementById("recDistMode");
    recDistMode.value = localStorage.getItem("bpsRecDistMode") || "calibrated";
    if (![...recDistMode.options].some(o => o.value === recDistMode.value)) recDistMode.value = "calibrated";
    // The three selectors live in an indented sub-row under the toggle, shown
    // as one unit only while the overlay is on.
    const recDistOptions = document.getElementById("recDistOptions");
    const showRecDistControls = () => {
        recDistOptions.style.display = recDistToggle.checked ? "flex" : "none";
    };
    showRecDistControls();
    recDistCount.addEventListener("change", () => {
        localStorage.setItem("bpsRecDistCount", recDistCount.value);
        if (img.naturalWidth > 0 && !drawToolActive()) redrawAll();
    });
    recDistColor.addEventListener("change", () => {
        localStorage.setItem("bpsRecDistColor", recDistColor.value);
        if (img.naturalWidth > 0 && !drawToolActive()) redrawAll();
    });
    recDistMode.addEventListener("change", () => {
        localStorage.setItem("bpsRecDistMode", recDistMode.value);
        if (img.naturalWidth > 0 && !drawToolActive()) redrawAll();
    });
    recDistToggle.addEventListener("change", async () => {
        localStorage.setItem("bpsRecDist", recDistToggle.checked ? "on" : "off");
        showRecDistControls();
        focusedRecDistLink = null; // start a fresh session with nothing isolated
        if (recDistToggle.checked) {
            // Judge what we have only AFTER the re-poll, so a toggle right
            // after page load doesn't toast "no data" while the fetch is still
            // in flight — and use the painter's own link computation, so "a
            // result exists but nothing is drawable" (receivers re-linked or
            // renamed since the solve) gets called out instead of a silently
            // empty map.
            await pollCalibration();
            const { links, result, matchedCount } = receiverDistanceLinks();
            if (!result) {
                bpsToast("No calibration data for this floor yet — run a calibration from the Calibration tab first.");
            } else if (!matchedCount) {
                bpsToast("The floor's calibration data no longer matches its placed receivers (re-linked or renamed since the solve?) — run a new calibration.");
            } else if (!links.length) {
                bpsToast("No links match the current colour filter — pick a different colour or 'All colours'.");
            }
        }
        if (img.naturalWidth > 0 && !drawToolActive()) redrawAll();
    });

    // =================================================================
    // Distance grid overlay (toggleable, meters or feet)
    // =================================================================

    let gridUnit = localStorage.getItem("bpsGridUnit") || "off"; // off | m | ft
    const gridToggle = document.getElementById("gridToggle");

    function updateGridButton() {
        // Short units ("m"/"ft") keep every label narrow enough to sit on one
        // line; a fixed button width (CSS) stops it hopping to a new row as the
        // label changes.
        gridToggle.textContent = gridUnit === "off" ? "Grid: off"
            : gridUnit === "m" ? "Grid: m" : "Grid: ft";
    }
    updateGridButton();

    gridToggle.addEventListener("click", () => {
        gridUnit = gridUnit === "off" ? "m" : gridUnit === "m" ? "ft" : "off";
        localStorage.setItem("bpsGridUnit", gridUnit);
        updateGridButton();
        // Redraw only when a floor plan is actually loaded; the preference
        // itself always cycles and persists.
        if (img.naturalWidth > 0) {
            clearCanvas();
            drawElements();
        }
    });

    function drawGrid() {
        if (gridUnit === "off") return;
        const floor = finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
        const scale = floor && floor.scale; // pixels per meter
        if (!scale) return;
        const unitPx = gridUnit === "m" ? scale : scale * 0.3048;
        // Thin the grid out when single units would be too dense on screen
        // at the current zoom level.
        let step = unitPx;
        let unitsPerLine = 1;
        while (step * view.zoom < 45) {
            step += unitPx;
            unitsPerLine += 1;
        }
        // Labels pinned to the visible edges, constant size on screen.
        const topWorld = -view.y / view.zoom;
        const leftWorld = -view.x / view.zoom;
        ctx.save();
        ctx.strokeStyle = "rgba(30, 60, 120, 0.18)";
        ctx.lineWidth = 1 / view.zoom;
        ctx.fillStyle = "rgba(30, 60, 120, 0.75)";
        ctx.font = `${14 / view.zoom}px system-ui, sans-serif`;
        for (let gx = step, i = unitsPerLine; gx < canvas.width; gx += step, i += unitsPerLine) {
            ctx.beginPath();
            ctx.moveTo(gx, 0);
            ctx.lineTo(gx, canvas.height);
            ctx.stroke();
            ctx.fillText(`${i}${gridUnit}`, gx + 3 / view.zoom, topWorld + 16 / view.zoom);
        }
        for (let gy = step, i = unitsPerLine; gy < canvas.height; gy += step, i += unitsPerLine) {
            ctx.beginPath();
            ctx.moveTo(0, gy);
            ctx.lineTo(canvas.width, gy);
            ctx.stroke();
            ctx.fillText(`${i}${gridUnit}`, leftWorld + 3 / view.zoom, gy - 4 / view.zoom);
        }
        ctx.restore();
    }

    // Display selected map
    async function selectExistingMap(value) {
        // Abandon any in-progress draw/edit so its handlers and half-built
        // polygon can't bleed onto the newly-selected floor.
        removeListeners();
        buttonreset();
        zonePoints = [];
        selectedVertex = null;
        draggingZone = false;
        editTarget = null;
        img.src = `/local/bps_maps/${value}`;
        imgfilename = value;
        mapname.value = removeExtension(value);
        SelMapName = mapname.value;
        await setupCanvasWithImage(img, canvas);
        new_floor = false;
        drawElements();
    }

    mapSelector.addEventListener('change', async () => {
        if (!mapSelector.value) return;
        await selectExistingMap(mapSelector.value);
    });

    upload.addEventListener('change', event => {
        const file = event.target.files[0];
        if (!file) return;

        // A new image switches floors: drop any open adjust preview so its
        // (previous-floor) ghost/bar can't linger or apply onto the new floor.
        cancelAdjust();

        // A new image invalidates any running tracking session (it iterates
        // the selected floor's receivers, which are about to change).
        stoptrackstat = true;

        // Switch the selection to the new floor right away. Leaving the
        // previous floor selected kept ITS receivers listed in the sidebar
        // under the new image, where deleting them silently edited that floor.
        mapname.value = removeExtension(file.name);
        SelMapName = mapname.value;

        const reader = new FileReader();
        reader.onload = function () {
            img.src = reader.result;
            setupCanvasWithImage(img, canvas).then(() => {
                drawElements();
            });
        };
        reader.readAsDataURL(file);
        new_floor = true;
    });

    function setupCanvasWithImage(img, canvas) {
        return new Promise((resolve) => {
            const ctx = canvas.getContext('2d');
            
            img.onload = () => {
                setupImageSize(img, canvas);
                resolve(); // Resolve when completed
            };
            img.onerror = () => {
                // Settle the promise so callers (including the startup
                // auto-open) continue instead of hanging forever.
                console.error(`Failed to load floor image: ${img.src}`);
                messdiv.innerHTML = '<p class="text-sm text-gray-500">Could not load the floor image for this map. Re-select it or upload a new image.</p>';
                resolve();
            };
    
            // Add the buttons
            drawAreaButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&amp;_svg]:pointer-events-none [&amp;_svg]:size-4 [&amp;_svg]:shrink-0 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2';
            drawAreaButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pencil w-4 h-4 mr-2" data-component-name="Pencil"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"></path><path d="m15 5 4 4"></path></svg>
                    Draw Zone
                `;
            drawAreaButton.setAttribute('data-active', 'false');

            drawSubZoneButton.className = drawAreaButton.className;
            drawSubZoneButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-box-select w-4 h-4 mr-2" data-component-name="SubZone"><rect x="3" y="3" width="18" height="18" rx="2"></rect><rect x="8" y="8" width="8" height="8" rx="1"></rect></svg>
                    Draw Sub-Zone
                `;
            drawSubZoneButton.setAttribute('data-active', 'false');

            addDeviceButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2';
            addDeviceButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-radio w-4 h-4 mr-2" data-component-name="Radio"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"></path><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"></path><circle cx="12" cy="12" r="2"></circle><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"></path><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"></path></svg>
                    Place Receiver
                `;
            addDeviceButton.setAttribute('data-active', 'false');

            SetScaleButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2';
            SetScaleButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-ruler w-4 h-4 mr-2" data-component-name="Ruler"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"></path><path d="m14.5 12.5 2-2"></path><path d="m11.5 9.5 2-2"></path><path d="m8.5 6.5 2-2"></path><path d="m17.5 15.5 2-2"></path></svg>
                    Set Scale
                `;
            SetScaleButton.setAttribute('data-active', 'false');
            
            clearCanvasButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2';
            clearCanvasButton.innerHTML = `
                <svg width="24px" height="24px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9 9L15 15" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 9L9 15" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="12" r="9" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    Clear Canvas
                `;
            
            saveButton.className = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&amp;_svg]:pointer-events-none [&amp;_svg]:size-4 [&amp;_svg]:shrink-0 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2';
            saveButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-save w-4 h-4 mr-2" data-component-name="Save"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"></path><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"></path><path d="M7 3v4a1 1 0 0 0 1 1h7"></path></svg>
                    Save Floor Plan
                `;
            
            adjustZonesButton.className = drawAreaButton.className;
            adjustZonesButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-wand w-4 h-4 mr-2" data-component-name="Wand"><path d="m3 21 9-9"></path><path d="M15 4V2"></path><path d="M15 16v-2"></path><path d="M8 9h2"></path><path d="M20 9h2"></path><path d="M17.8 11.8 19 13"></path><path d="M15 9h.01"></path><path d="M17.8 6.2 19 5"></path><path d="M12.2 6.2 11 5"></path></svg>
                    Adjust Zones
                `;
            adjustZonesButton.setAttribute('data-active', 'false');

            adjustSubZonesButton.className = drawAreaButton.className;
            adjustSubZonesButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-wand w-4 h-4 mr-2" data-component-name="WandSub"><path d="m3 21 9-9"></path><path d="M15 4V2"></path><path d="M15 16v-2"></path><path d="M8 9h2"></path><path d="M20 9h2"></path><path d="M17.8 11.8 19 13"></path><path d="M15 9h.01"></path><path d="M17.8 6.2 19 5"></path><path d="M12.2 6.2 11 5"></path></svg>
                    Adjust Sub-zones
                `;
            adjustSubZonesButton.setAttribute('data-active', 'false');

            mapbuttondiv.appendChild(addDeviceButton);
            mapbuttondiv.appendChild(drawAreaButton);
            mapbuttondiv.appendChild(drawSubZoneButton);
            mapbuttondiv.appendChild(SetScaleButton);
            mapbuttondiv.appendChild(adjustZonesButton);
            mapbuttondiv.appendChild(adjustSubZonesButton);
            mapbuttondiv.appendChild(clearCanvasButton);
        });
    }


    function setupImageSize(img, canvas, fixedWidth = 2000) {
        const ctx = canvas.getContext('2d');
    
        const imgratio = img.height / img.width;
        const newwidth = fixedWidth; // Fixed width in pixels
        const newheight = newwidth * imgratio; // Height based on aspect ratio
    
        // Update canvas size (this also resets the canvas transform)
        canvas.width = newwidth;
        canvas.height = newheight;

        // A new floor image starts from the default viewport.
        view.zoom = 1;
        view.x = 0;
        view.y = 0;
    
        // Draw image on canvas
        ctx.drawImage(img, 0, 0, newwidth, newheight);
    }
    

    function removeExtension(fileName) {
        const lastDotIndex = fileName.lastIndexOf('.');
        if (lastDotIndex === -1) {
            return fileName;
        }
        return fileName.substring(0, lastDotIndex);
    }

    // Save data
    saveButton.addEventListener('click', async () => {
        let saveresult = await savedata();
        if(saveresult){
            tmpfinalcords = finalcords;
            saveButton.remove();
            bpsToast('Saved successfully!');
            getSavedMaps();
            // Placements changed: re-render the calibration report so its
            // missing-receiver block reconciles against the new data now
            // (the idle-state poll never fires on its own), and refresh the
            // linking snapshot the sidebar/Debugging tab read.
            pollCalibration();
            if (!scannerLinkingLoading) loadScannerLinking();
        }
    });

    // =================================================================
    // Adjust zones — square boxy rooms, snap shared boundaries, remove
    // overlaps. Previews the backend proposal (green ghost) before applying.
    // =================================================================
    function currentFloor() {
        return finalcords.floor.find(f => sameFloorName(f.name, SelMapName));
    }

    adjustZonesButton.addEventListener('click', () => {
        // Same button toggles closed; the other switches the preview target.
        if (adjustPreview && adjustTarget === 'zones') { cancelAdjust(); return; }
        openAdjustPreview('zones');
    });
    adjustSubZonesButton.addEventListener('click', () => {
        if (adjustPreview && adjustTarget === 'subzones') { cancelAdjust(); return; }
        openAdjustPreview('subzones');
    });

    async function openAdjustPreview(target) {
        // Validate the target set BEFORE tearing down any open preview, so
        // clicking the other Adjust button on a floor that lacks that set is a
        // no-op + toast, not silent destruction of the current preview.
        const floor = currentFloor();
        if (!floor) { bpsToast('Select a floor first.'); return; }
        if (target === 'subzones') {
            if (!Array.isArray(floor.subzones) || floor.subzones.length < 1) {
                bpsToast('Draw at least one sub-zone on this floor first.');
                return;
            }
        } else if (!Array.isArray(floor.zones) || floor.zones.length < 2) {
            bpsToast('Draw at least two zones on this floor first.');
            return;
        }
        buttonreset(); // leave any active draw tool / clear a stale preview
        adjustTarget = target;
        showAdjustBar(22); // ~27cm default at a typical scale
        await runAdjustPreview();
    }

    async function runAdjustPreview() {
        const floor = currentFloor();
        // #bpsAdjustActions is the "adjust UI open" sentinel; the knobs live in
        // the separate centered strip above the map.
        const open = document.getElementById('bpsAdjustActions');
        const tolEl = document.getElementById('bpsAdjustTol');
        const squareEl = document.getElementById('bpsAdjustSquare');
        const summary = document.getElementById('bpsAdjustSummary');
        if (!floor || !open || !tolEl || !squareEl || !summary) return;
        // Capture the run + floor + target so a slow response that arrives after
        // the user cancelled, switched floors/target, or moved the slider again
        // is dropped (no stale/wrong ghost; last change wins).
        const myFloor = SelMapName;
        const myTarget = adjustTarget;
        const myRun = ++adjustRunSeq;
        const tolPx = Number(tolEl.value);
        const square = squareEl.checked;
        summary.textContent = 'Computing…';
        try {
            const res = await bpsFetch('/api/bps/adjust_zones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target: myTarget,
                    zones: floor.zones,
                    subzones: floor.subzones || [],
                    options: { tolerance: tolPx, square },
                }),
            });
            const data = res.ok ? await res.json() : null;
            if (myRun !== adjustRunSeq || !document.getElementById('bpsAdjustActions')
                || !sameFloorName(SelMapName, myFloor)) {
                return; // superseded / cancelled / floor changed
            }
            if (!data) { summary.textContent = 'Adjust failed.'; return; }
            adjustPreview = {
                target: myTarget,
                zones: data.zones || [],
                subzones: data.subzones || [],
                changes: data.changes || [],
                warnings: data.warnings || [],
            };
            summary.textContent = adjustSummaryText(adjustPreview);
            if (mapReady()) redrawAll();
        } catch (e) {
            if (myRun === adjustRunSeq && document.getElementById('bpsAdjustActions')) {
                summary.textContent = 'Adjust failed.';
            }
        }
    }

    function adjustSummaryText(p) {
        const noun = p.target === 'subzones' ? 'sub-zones' : 'zones';
        const squared = p.changes.filter(c => c.squared).length;
        const moved = p.changes.filter(c => c.max_move_px > 1).length;
        const scale = (currentFloor() || {}).scale;
        const maxMove = p.changes.reduce((m, c) => Math.max(m, c.max_move_px || 0), 0);
        const cm = scale ? ` (max ${(maxMove / scale * 100).toFixed(0)}cm)` : '';
        const tail = p.target === 'subzones' ? 'clamped to parents' : 'overlaps removed';
        let t = `${noun}: ${squared} squared · ${moved} nudged${cm} · ${tail}`;
        if (p.warnings.length) t += ` · ${p.warnings.length} note(s)`;
        return t;
    }

    function showAdjustBar(defaultPx) {
        hideAdjustBar();
        const scale = (currentFloor() || {}).scale;
        const cmFor = px => scale ? `${(px / scale * 100).toFixed(0)}cm` : `${px}px`;
        // ✓ Apply / ✕ Cancel pinned to the map's top-left corner, exactly where
        // the layout tools show ✓ Save / ✕ Cancel. #bpsAdjustActions doubles as
        // the "adjust UI open" sentinel (created here, removed in hideAdjustBar).
        const actions = document.createElement('div');
        actions.id = 'bpsAdjustActions';
        actions.className = 'bps-adjust-actions';
        actions.innerHTML = `
            <button type="button" id="bpsAdjustApply">✓ Apply</button>
            <button type="button" id="bpsAdjustCancel">✕ Cancel</button>
        `;
        (document.querySelector('.bps-canvas-wrap') || document.body).appendChild(actions);
        actions.querySelector('#bpsAdjustApply').addEventListener('click', applyAdjust);
        actions.querySelector('#bpsAdjustCancel').addEventListener('click', cancelAdjust);

        // Summary + tuning knobs go in a centered strip ABOVE the map (a static
        // container between the setup row and the canvas), so they never cover
        // the zones being adjusted.
        const controls = document.getElementById('bpsAdjustControls');
        if (controls) {
            controls.innerHTML = `
                <span id="bpsAdjustSummary" class="bps-adjust-summary">Computing…</span>
                <label class="bps-adjust-ctl">Snap
                    <input type="range" id="bpsAdjustTol" min="6" max="60" step="2" value="${defaultPx}">
                    <span id="bpsAdjustTolVal">${cmFor(defaultPx)}</span>
                </label>
                <label class="bps-adjust-ctl"><input type="checkbox" id="bpsAdjustSquare" checked> Square rooms</label>
            `;
            controls.style.display = '';
            const tol = controls.querySelector('#bpsAdjustTol');
            const tolVal = controls.querySelector('#bpsAdjustTolVal');
            let debounce = null;
            tol.addEventListener('input', () => {
                tolVal.textContent = cmFor(Number(tol.value));
                clearTimeout(debounce);
                debounce = setTimeout(runAdjustPreview, 250);
            });
            controls.querySelector('#bpsAdjustSquare').addEventListener('change', runAdjustPreview);
        }
    }

    function hideAdjustBar() {
        const actions = document.getElementById('bpsAdjustActions');
        if (actions) actions.remove();
        const controls = document.getElementById('bpsAdjustControls');
        if (controls) { controls.innerHTML = ''; controls.style.display = 'none'; }
    }

    function cancelAdjust() {
        const had = adjustPreview || document.getElementById('bpsAdjustActions');
        adjustRunSeq++; // invalidate any in-flight preview response
        adjustPreview = null;
        hideAdjustBar();
        if (had && mapReady()) redrawAll();
    }

    function applyAdjust() {
        if (!adjustPreview) return;
        const floor = currentFloor();
        if (!floor) { cancelAdjust(); return; }
        // Apply only the set being adjusted into finalcords (not yet persisted —
        // Save Floor Plan writes it, reloading discards, matching every other
        // panel edit).
        const isSub = adjustPreview.target === 'subzones';
        if (isSub) {
            floor.subzones = adjustPreview.subzones;
        } else {
            floor.zones = adjustPreview.zones;
        }
        const warnings = adjustPreview.warnings;
        adjustPreview = null;
        hideAdjustBar();
        if (mapReady()) redrawAll();
        savebuttondiv.appendChild(saveButton);
        let msg = `${isSub ? 'Sub-zones' : 'Zones'} adjusted — review, then Save Floor Plan (reload to discard).`;
        if (warnings.length) msg += ` Note: ${warnings[0]}`;
        bpsToast(msg);
    }

    //When clicking the delete button, remove the floor and reset the canvas.
    deleteButton.addEventListener("click", async function () {
        const userConfirmed = await bpsConfirm(
            `Remove the floor "${SelMapName}"? This deletes its map, zones and sub-zones.`,
            { confirmText: "Delete floor", danger: true }
        );
        if (!userConfirmed) return;

        // Keep the removed entries so a failed save can restore them.
        const removedFloors = finalcords.floor.filter(floor => sameFloorName(floor.name, SelMapName));
        finalcords.floor = finalcords.floor.filter(floor => !sameFloorName(floor.name, SelMapName));

        // Remove the map image belonging to the floor being deleted — not
        // whichever file the dropdown happened to point at last.
        const mapFile = Array.from(mapSelector.options)
            .map(option => option.value)
            .find(value => sameFloorName(removeExtension(value), SelMapName));
        imgfilename = mapFile || "";
        removefile = Boolean(mapFile);

        // A delete is never a new-floor save: without this, savedata would
        // suppress the 'remove' field and upload any pending image instead.
        new_floor = false;
        upload.value = "";

        // Deleting must not be blocked by the scale requirement of normal saves.
        let saveresult = false;
        try {
            saveresult = await savedata(true);
        } finally {
            if (!saveresult) {
                finalcords.floor = finalcords.floor.concat(removedFloors); //If not able to delete, restore the array
            }
            removefile = false;
        }
        if(saveresult){
            bpsToast("The floor named "+SelMapName+" has been removed!");
            console.log("Updated data:", finalcords); // Control the updated data
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            mapname.value = "";
            getSavedMaps();
        }
    });

    async function savedata(skipScaleCheck = false){
        if(!skipScaleCheck && myScaleVal == null){
            bpsToast("You have not added a scale, it won't work without it!");
            return;
        }

        removeListeners();
        const data = new FormData();
        data.append('coordinates', JSON.stringify(finalcords)); 
        data.append('new_floor', new_floor);

        if(removefile === true && new_floor === false){
            data.append('remove', imgfilename);
        }

        if(new_floor){ // Add filedata to variable 'data' if there is a new floor
            const file = upload.files[0];
            if (!file) {
                bpsToast("No floor image is selected — please choose the floor image again.");
                return;
            }
            const extension = file.name.substring(file.name.lastIndexOf('.')); // Get the old file ending
            // Reuse the exact name of an already saved map for this floor so
            // re-uploads overwrite it instead of forking a case-variant file.
            const existingMap = Array.from(mapSelector.options)
                .map(option => option.value)
                .find(value => value && sameFloorName(removeExtension(value), SelMapName));
            const newFileName = existingMap
                ? removeExtension(existingMap) + extension
                : `${SelMapName}${extension}`; // Build the new filename
            const renamedFile = new File([file], newFileName, { type: file.type });

            if (renamedFile) {
                data.append('file', renamedFile);
            } else {
                console.log("No file uploaded.");
            }
        }

        try {
            const response = await bpsFetch('/api/bps/save_text', {
                method: 'POST',
                body: data,
            });
            if (response.ok) {
                drawAreaButton.remove();
                addDeviceButton.remove();
                clearCanvasButton.remove();
                SetScaleButton.remove();
                saveButton.remove();
                new_floor = false;
                return true;
            } else {
                bpsToast('Error saving data!');
            }
        } catch (error) {
            console.error('Error saving data:', error);
            bpsToast('Error saving data!');
        }
    }

    // =================================================================
    // Receiver calibration
    // =================================================================

    const calibStart = document.getElementById('calibStart');
    const calibCancel = document.getElementById('calibCancel');
    const calibApply = document.getElementById('calibApply');
    const calibReset = document.getElementById('calibReset');
    const calibStatus = document.getElementById('calibStatus');
    const calibResults = document.getElementById('calibResults');
    const calibDuration = document.getElementById('calibDuration');
    const calibAuto = document.getElementById('calibAuto');
    const calibManualControls = document.getElementById('calibManualControls');
    let calibTimer = null;
    let calibLastResults = {};

    // Calibration-tab callers key off the Floor-name box (mapname.value); the
    // map overlay passes SelMapName instead, so mid-rename typing can't detach
    // the overlay from the floor actually on screen.
    function selectedFloorResult(results, floorName = mapname.value) {
        for (const name of Object.keys(results || {})) {
            if (sameFloorName(name, floorName)) return results[name];
        }
        return null;
    }

    async function calibRequest(body) {
        const res = await bpsFetch('/api/bps/calibration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `Calibration request failed (${res.status})`);
        return data;
    }

    // The missing lists are baked into the solve-result snapshot, but
    // placements can change afterwards (re-link, add, remove + save).
    // Reconcile against the CURRENT floor data so a replaced receiver drops
    // out immediately instead of being reported missing until the next solve,
    // and anything placed since the solve is listed as pending, not missing.
    function calibMissingNow(result) {
        const floorNow = (finalcords.floor || []).find(f => sameFloorName(f.name, result.floor));
        const placedNow = floorNow
            ? new Set((floorNow.receivers || []).map(r => r && r.entity_id).filter(Boolean))
            : null;
        const still = list => placedNow ? list.filter(s => placedNow.has(s)) : list.slice();
        const missUnmatched = still(result.missing_unmatched || []);
        const missNoData = still(result.missing_no_data || []);
        let placedSince = [];
        if (placedNow) {
            const inReport = new Set([
                ...Object.keys(result.receivers || {}),
                ...(result.missing_unmatched || []),
                ...(result.missing_no_data || []),
            ]);
            placedSince = [...placedNow].filter(s => !inReport.has(s)).sort();
        }
        return { missUnmatched, missNoData, placedSince };
    }

    function renderCalibrationResult(result) {
        const miss = calibMissingNow(result);
        const missingCount = miss.missUnmatched.length + miss.missNoData.length;
        calibStatus.textContent =
            `Floor ${result.floor}: ${result.pairs_used} pairs (${result.bidirectional_pairs} bidirectional), ` +
            `typical error ×${result.error_factor_before} → ×${result.error_factor_after} predicted after correction.` +
            (missingCount ? ` ${missingCount} placed receiver${missingCount > 1 ? "s" : ""} missing — see below.` : "");

        const slugs = Object.keys(result.receivers).sort();
        const cells = {};
        (result.matrix || []).forEach(m => { cells[`${m.tx}|${m.rx}`] = m; });
        const lowConfidence = result.low_confidence || [];

        let html = '<table style="border-collapse:collapse; font-size:11px; margin-top:8px">'
            + '<tr><th style="text-align:left; padding:2px 6px">tx \\ rx</th>';
        slugs.forEach(s => {
            html += `<th class="bps-calib-colhead"><div><span>${escHtml(s)}</span></div></th>`;
        });
        html += '<th class="bps-calib-colhead"><div><span>correction</span></div></th></tr>';
        slugs.forEach(tx => {
            html += `<tr><td style="padding:2px 6px; white-space:nowrap">${escHtml(tx)}${lowConfidence.includes(tx) ? ' ⚠' : ''}</td>`;
            slugs.forEach(rx => {
                const m = cells[`${tx}|${rx}`];
                if (!m) {
                    html += '<td style="background:#eee"></td>';
                    return;
                }
                // Blue = measuring short, green = accurate, red = measuring long.
                const p = Math.max(-1, Math.min(1, m.error_pct / 100));
                const hue = 240 - (p + 1) * 120;
                html += `<td title="true ${m.true_m} m · measured ${m.measured_m} m · corrected ${m.corrected_m} m · ${m.samples} samples" `
                    + `style="background:hsl(${hue},55%,55%); color:#fff; text-align:center; padding:2px 4px">`
                    + `${m.error_pct > 0 ? '+' : ''}${Math.round(m.error_pct)}%</td>`;
            });
            html += `<td style="text-align:center; padding:2px 6px">×${result.receivers[tx]}</td></tr>`;
        });
        html += '</table>';
        if (lowConfidence.length) {
            html += `<p class="text-sm text-gray-500" style="margin-top:6px">⚠ Low confidence (aggressive correction or few pairs): ${escHtml(lowConfidence.join(', '))} — verify those receivers before applying.</p>`;
        }
        // Placed receivers absent from the matrix, with WHY (issue #63): the
        // report is built only from scanners that produced matched samples, so
        // without this a drifted or silent scanner just vanished. Lists come
        // from calibMissingNow, reconciled against the current placements —
        // which include UNSAVED edits, so say so (and if unsaved edits emptied
        // the list, keep the block with just the note rather than silently
        // hiding a receiver the backend still reports missing).
        const unsavedEdits = savebuttondiv.contains(saveButton);
        const rawMissing = (result.missing_unmatched || []).length + (result.missing_no_data || []).length;
        if (miss.missUnmatched.length || miss.missNoData.length || miss.placedSince.length || (unsavedEdits && rawMissing)) {
            html += '<div class="bps-calib-missing">'
                + '<div class="bps-calib-missing-title">Placed on this floor but missing from this report</div>';
            if (miss.missUnmatched.length) {
                html += `<p><strong>No matching Bermuda scanner:</strong> ${escHtml(miss.missUnmatched.join(', '))} — `
                    + 'the device name no longer matches the placed id (usually a rename after moving the probe). '
                    + 'Check the <strong>Debugging</strong> tab, or rename the device/entity so they match.</p>';
            }
            if (miss.missNoData.length) {
                html += `<p><strong>Matched, but no beacon samples:</strong> ${escHtml(miss.missNoData.join(', '))} — `
                    + 'the scanner was found but produced no usable probe-to-probe adverts. '
                    + 'Check the probe is advertising its iBeacon (or sample longer).</p>';
            }
            if (miss.placedSince.length) {
                html += `<p><strong>Placed since this report:</strong> ${escHtml(miss.placedSince.join(', '))} — `
                    + 'will be included on the next calibration run (auto mode re-solves every 15 minutes).</p>';
            }
            if (unsavedEdits) {
                html += '<p class="bps-calib-missing-note">Reflects unsaved edits — Save Floor Plan to apply them.</p>';
            }
            html += '</div>';
        }
        calibResults.innerHTML = html;
    }

    function renderCalibration(status) {
        const auto = status.mode === 'auto';
        const manualSampling = status.mode === 'manual' && status.state === 'sampling';
        calibLastResults = status.results || {};
        calibAuto.checked = auto;
        calibManualControls.style.display = auto ? 'none' : '';
        calibStart.style.display = manualSampling ? 'none' : '';
        calibCancel.style.display = manualSampling ? '' : 'none';
        const result = selectedFloorResult(calibLastResults);
        // Auto mode applies by itself; the button is for manual runs only.
        calibApply.style.display = !auto && result ? '' : 'none';

        const pairs = Object.keys(status.pair_counts || {}).length;
        if (auto) {
            if (result) renderCalibrationResult(result);
            else calibResults.innerHTML = '';
            // Set the status line AFTER rendering the result, which writes its
            // own summary into it; the auto line carries the result summary too.
            let line = `Auto calibration running · ${pairs} receiver pairs in the window`;
            if (status.error) line += ` · ${status.error}`;
            else if (status.last_solved_at) line += ` · last solve ${status.last_solved_at}`;
            else line += ' · first solve after a few minutes of data';
            if (result) {
                line += ` · floor ${result.floor}: ${result.pairs_used} pairs used, `
                    + `typical error ×${result.error_factor_before} → ×${result.error_factor_after}`;
                // Keep the missing-receiver pointer (issue #63) — this line
                // replaces the one renderCalibrationResult just wrote. Same
                // reconciled lists so a replaced receiver isn't counted.
                const m = calibMissingNow(result);
                const missing = m.missUnmatched.length + m.missNoData.length;
                if (missing) line += ` · ${missing} placed receiver${missing > 1 ? "s" : ""} missing — see below`;
            }
            calibStatus.textContent = line;
            return;
        }
        if (manualSampling) {
            const total = status.duration || 1;
            const left = status.seconds_left || 0;
            const done = total - left;
            calibStatus.textContent =
                `Sampling floor ${status.floor}… ${Math.floor(done / 60)}:${String(done % 60).padStart(2, '0')}`
                + ` of ${Math.floor(total / 60)} min · ${pairs} receiver pairs heard so far.`;
            return;
        }
        if (status.state === 'error') {
            calibStatus.textContent = `Calibration failed: ${status.error}`;
            return;
        }
        if (result) {
            renderCalibrationResult(result);
            return;
        }
        calibStatus.textContent = 'Idle. Select a floor, then start a run — or enable auto calibration.';
        calibResults.innerHTML = '';
    }

    async function pollCalibration() {
        try {
            const res = await bpsFetch('/api/bps/calibration');
            if (!res.ok) return;
            const status = await res.json();
            renderCalibration(status);
            // The receiver-distances overlay renders from these results, so a
            // fresh solve should show on the map without a manual repaint. Same
            // guards as fetchReceiverStatus: never mid-draw/edit (a repaint
            // would wipe the tool overlay), and never mid-tracking (that loop
            // repaints every tick and will pick the new results up on its own).
            if (recDistToggle.checked && mapReady() && !drawToolActive() && !editTarget && !pollTrackActive) redrawAll();
            const wantInterval = status.mode === 'auto' ? 10000
                : status.state === 'sampling' ? 3000 : 0;
            if (calibTimer) { clearInterval(calibTimer); calibTimer = null; }
            if (wantInterval) calibTimer = setInterval(pollCalibration, wantInterval);
        } catch (e) {
            console.warn('Calibration status:', e);
        }
    }

    calibAuto.addEventListener('change', async () => {
        try {
            renderCalibration(await calibRequest({ action: 'auto', enabled: calibAuto.checked }));
            pollCalibration();
        } catch (e) {
            calibAuto.checked = !calibAuto.checked;
            bpsToast(e.message);
        }
    });

    // Switching floors should switch the displayed matrix too.
    mapSelector.addEventListener('change', () => {
        const result = selectedFloorResult(calibLastResults);
        if (result) renderCalibrationResult(result);
        else calibResults.innerHTML = '';
    });

    calibStart.addEventListener('click', async () => {
        if (!mapname.value) {
            bpsToast('Select a floor first.');
            return;
        }
        calibResults.innerHTML = '';
        try {
            renderCalibration(await calibRequest({
                action: 'start',
                floor: mapname.value,
                duration: Number(calibDuration.value),
            }));
            if (!calibTimer) calibTimer = setInterval(pollCalibration, 3000);
        } catch (e) {
            bpsToast(e.message);
        }
    });

    calibCancel.addEventListener('click', async () => {
        try {
            renderCalibration(await calibRequest({ action: 'cancel' }));
        } catch (e) {
            bpsToast(e.message);
        }
    });

    calibApply.addEventListener('click', async () => {
        // Applying reloads bpsdata.txt from disk (below), which would silently
        // discard any unsaved layout edit (moved receiver, height, zone colour)
        // while the sidebar kept showing it — the badge and Save button would
        // lie. Block instead of losing work; heights in particular route users
        // here ("recalibrate after changing it").
        if (savebuttondiv.contains(saveButton)) {
            bpsToast("Save Floor Plan first — applying reloads the floor data and would discard your unsaved edits.");
            return;
        }
        try {
            const data = await calibRequest({ action: 'apply', floor: mapname.value });
            bpsToast(`Corrections applied to ${data.applied} receiver(s).`);
            // The backend edited bpsdata.txt; reload so a later panel save
            // does not overwrite the corrections with stale data.
            await fetchBPSData();
        } catch (e) {
            bpsToast(e.message);
        }
    });

    calibReset.addEventListener('click', async () => {
        if (!mapname.value) {
            bpsToast('Select a floor first.');
            return;
        }
        // Same reload-from-disk hazard as Apply: don't discard unsaved edits.
        if (savebuttondiv.contains(saveButton)) {
            bpsToast("Save Floor Plan first — resetting reloads the floor data and would discard your unsaved edits.");
            return;
        }
        const warning = calibAuto.checked
            ? `Remove calibration corrections from floor "${mapname.value}"? Auto calibration is on and will learn and re-apply them again.`
            : `Remove calibration corrections from floor "${mapname.value}"?`;
        if (!(await bpsConfirm(warning, { confirmText: "Remove", danger: true }))) return;
        try {
            const data = await calibRequest({ action: 'reset', floor: mapname.value });
            bpsToast(`Corrections removed from ${data.reset} receiver(s).`);
            await fetchBPSData();
        } catch (e) {
            bpsToast(e.message);
        }
    });

    pollCalibration();

    // Tab switching: show one panel at a time. The Map tab is active in the
    // markup so the canvas is visible (and sized) on load; the calibration
    // poll keeps running regardless of which tab is showing.
    const tabButtons = document.querySelectorAll(".bps-tab");
    const tabPanels = document.querySelectorAll(".bps-tabpanel");
    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const name = btn.dataset.tab;
            tabButtons.forEach((b) => b.classList.toggle("active", b === btn));
            tabPanels.forEach((pnl) => pnl.classList.toggle("active", pnl.dataset.tabpanel === name));
            scheduleSidebarSync(); // sidebar becomes visible/hidden with the tab
            // Opening the Debugging tab re-checks the linking snapshot so its live
            // readings are current (they drift as devices move / go out of range).
            if (name === "debugging" && !scannerLinkingLoading) loadScannerLinking();
        });
    });

    // Cap the Zones & Receivers sidebar at the bottom of the viewport so a long
    // receiver list scrolls inside it instead of running off-screen. In the
    // stacked (narrow) layout the sidebar isn't sticky, so leave it uncapped.
    let sidebarRaf = null;
    function syncSidebarHeight() {
        const sb = document.querySelector(".bps-sidebar");
        if (!sb) return;
        if (getComputedStyle(sb).position !== "sticky") {
            sb.style.maxHeight = "";
            return;
        }
        const top = sb.getBoundingClientRect().top;
        sb.style.maxHeight = Math.max(200, window.innerHeight - top - 12) + "px";
    }
    function scheduleSidebarSync() {
        if (sidebarRaf) return;
        sidebarRaf = requestAnimationFrame(() => { sidebarRaf = null; syncSidebarHeight(); });
    }
    window.addEventListener("resize", scheduleSidebarSync);
    window.addEventListener("scroll", scheduleSidebarSync, { passive: true });
    syncSidebarHeight();

    // Light / dark theme toggle. The `dark` class on <html> and <body> drives
    // the CSS variable set; without it the light (:root) variables apply.
    const themeToggle = document.getElementById("themeToggle");
    function applyTheme(theme) {
        const dark = theme !== "light";
        document.documentElement.classList.toggle("dark", dark);
        document.body.classList.toggle("dark", dark);
        if (themeToggle) {
            themeToggle.textContent = dark ? "🌙" : "☀️";
            themeToggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
        }
    }
    applyTheme(localStorage.getItem("bpsTheme") || "dark");
    if (themeToggle) {
        themeToggle.addEventListener("click", () => {
            const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
            localStorage.setItem("bpsTheme", next);
            applyTheme(next);
        });
    }

    // Help tooltips open downward by default (so ones near the top of the page
    // aren't clipped), but the Tracking / Calibration controls sit low in the
    // panel — a downward tip there runs off the bottom of the (often short)
    // sidebar viewport. On hover, measure the tip and flip it above the icon
    // when it wouldn't fit below. Measuring works while it's still hidden
    // (visibility:hidden keeps layout), so the decision is made before it shows.
    document.querySelectorAll(".tooltip").forEach(tt => {
        tt.addEventListener("mouseenter", () => {
            const tip = tt.querySelector(".tooltip-text");
            if (!tip) return;
            const icon = tt.getBoundingClientRect();
            const tipH = tip.getBoundingClientRect().height;
            tt.classList.toggle("flip-up", icon.bottom + tipH + 16 > window.innerHeight);
        });
    });

    // With a single configured floor there is nothing to choose: open it
    // right away. This must run LAST — drawElements touches state declared
    // throughout this closure, so everything has to be initialized first.
    if (tmpsaved) {
        const savedMaps = Array.from(mapSelector.options)
            .map(option => option.value)
            .filter(Boolean);
        if (savedMaps.length === 1) {
            mapSelector.value = savedMaps[0];
            await selectExistingMap(savedMaps[0]);
        }
    }

});

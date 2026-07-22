// BPS custom panel — a thin courier.
//
// The BPS setup app is a standalone page served at /bps/index.html. It used to
// be shown as a bare Home Assistant `iframe` panel, which has no access to the
// logged-in user's token — so the /api/bps/* endpoints had to be left
// unauthenticated. This element is registered as a `panel_custom` instead, so
// Home Assistant sets `hass` on it; it keeps hosting the app in an inner iframe
// (no rewrite of the app) and simply forwards the current access token in via
// postMessage. The app attaches that token as a Bearer header on every API
// call, and the endpoints now require auth.
class BpsPanel extends HTMLElement {
  constructor() {
    super();
    this._iframe = null;
    this._lastToken = null;
    this._onMessage = this._onMessage.bind(this);
    // Register on the constructor, not connectedCallback: HA may detach and
    // re-attach the SAME element instance (e.g. after the tab is backgrounded),
    // and the inner iframe reloads on re-attach. A listener added in
    // connectedCallback would be removed on detach and — because the reconnect
    // path early-returns on the existing iframe — never re-added, so the
    // reloaded app's "bps-ready" would go unheard and every API call would 401.
    window.addEventListener("message", this._onMessage);
  }

  set hass(hass) {
    this._hass = hass;
    this._pushToken(); // fires on every hass update -> covers token refresh
  }

  set narrow(_v) {}
  set route(_v) {}
  set panel(_v) {}

  connectedCallback() {
    if (this._iframe) {
      // Reconnect (same instance re-attached): the iframe reloads, so re-arm
      // the token once its app comes back up.
      this._lastToken = null;
      this._pushToken(true);
      return;
    }
    this.style.display = "block";
    this.style.height = "100%";
    this.style.width = "100%";

    const iframe = document.createElement("iframe");
    iframe.src = "/bps/index.html";
    iframe.setAttribute("title", "BPS");
    iframe.style.border = "0";
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.display = "block";
    this._iframe = iframe;

    this.appendChild(iframe);
  }

  _onMessage(event) {
    if (event.origin !== window.location.origin) return;
    if (!this._iframe || event.source !== this._iframe.contentWindow) return;
    if (event.data === "bps-ready") {
      this._pushToken(true); // force: a freshly (re)loaded app has no token yet
    }
  }

  _token() {
    const auth = this._hass && this._hass.auth;
    if (!auth) return null;
    // home-assistant-js-websocket exposes `accessToken`; older builds only had
    // `data.access_token`. Accept either.
    return auth.accessToken || (auth.data && auth.data.access_token) || null;
  }

  async _pushToken(force) {
    if (!this._iframe) return;
    const cw = this._iframe.contentWindow;
    if (!cw) return;
    // Refresh an expired token before couriering it: HA does not proactively
    // refresh the access token for the manual /api/bps/* fetches the app makes,
    // so without this the app keeps sending a dead Bearer and every poll 401s —
    // which HA's http.ban counts toward banning the client's IP.
    const auth = this._hass && this._hass.auth;
    if (auth && auth.expired && typeof auth.refreshAccessToken === "function") {
      // De-dupe: `set hass` fires many times a second, so cache the in-flight
      // refresh and have concurrent ticks await the same one instead of each
      // firing its own /auth/token request while the token is expired.
      try {
        this._refreshing = this._refreshing
          || auth.refreshAccessToken().finally(() => { this._refreshing = null; });
        await this._refreshing;
      } catch (e) { /* send what we have */ }
      // The element may have detached (and the iframe changed) during the await.
      if (!this._iframe || this._iframe.contentWindow !== cw) return;
    }
    const token = this._token();
    if (!token) return;
    if (!force && token === this._lastToken) return;
    cw.postMessage({ type: "bps-auth", token }, window.location.origin);
    this._lastToken = token;
  }
}

customElements.define("bps-panel", BpsPanel);

/* AI Enterprise OS — Dashboard client (Phase 1, WS-5.0)
   Runs under a strict CSP: no inline scripts, no unsafe-eval.
   Responsibilities:
     - staleness ticker: poll /api/health every N seconds, show age
     - mermaid: render any <pre class="mermaid-source"> block client-side
     - markdown: render [data-md] blocks through marked + DOMPurify
     - events panel: WebSocket feed with auto-reconnect + dedupe
*/

(function () {
  "use strict";

  var POLL_MS = parseInt(
    document.body.getAttribute("data-poll-interval-ms") || "5000",
    10
  );
  var WS_URL = "ws://" + location.host + "/api/ws";
  var stalenessEl = document.getElementById("staleness");
  var lastPollAt = null;

  /* ── Staleness ticker (R9/WS-5.0) ───────────────────────────────────── */
  function updateStaleness() {
    if (!stalenessEl) return;
    if (!lastPollAt) {
      stalenessEl.textContent = "connecting…";
      return;
    }
    var ageSec = Math.max(0, Math.round((Date.now() - lastPollAt) / 1000));
    stalenessEl.textContent = "last health poll: " + ageSec + "s ago";
    stalenessEl.classList.remove("late", "stale");
    if (ageSec > POLL_MS / 1000 * 3) {
      stalenessEl.classList.add("late");
    }
    if (ageSec > POLL_MS / 1000 * 6) {
      stalenessEl.classList.add("stale");
    }
  }

  async function pollHealth() {
    try {
      var resp = await fetch("/api/health", { headers: { "Accept": "application/json" } });
      if (!resp.ok) return;
      var body = await resp.json();
      lastPollAt = Date.now();
      var el = document.querySelector("[data-health-chip]");
      if (el && body.status) {
        el.textContent = body.status;
        el.className = "chip " + (body.status === "ok" ? "ok" : body.status === "degraded" ? "watch" : "action");
      }
    } catch (e) {
      /* network hiccup: keep last value, staleness indicator will grow */
    }
    updateStaleness();
  }

  /* ── Markdown via marked + DOMPurify (R11) ───────────────────────────── */
  function renderMarkdown() {
    if (!window.marked || !window.DOMPurify) return;
    document.querySelectorAll("[data-md]").forEach(function (el) {
      if (el.dataset.mdRendered) return;
      var raw = el.textContent || "";
      var html = window.marked.parse(raw);
      el.innerHTML = window.DOMPurify.sanitize(html);
      el.dataset.mdRendered = "1";
    });
  }

  /* ── Mermaid (org chart) via DOMPurify first (R11) ───────────────────── */
  function renderMermaid() {
    if (!window.mermaid) return;
    var blocks = document.querySelectorAll("pre.mermaid-source");
    if (!blocks.length) return;
    try { window.mermaid.initialize({ startOnLoad: false, theme: "dark" }); } catch (e) { return; }
    blocks.forEach(function (pre) {
      if (pre.dataset.rendered) return;
      var source = pre.textContent || "";
      var container = document.createElement("div");
      container.className = "mermaid-box";
      pre.parentNode.replaceChild(container, pre);
      var safe = window.DOMPurify ? window.DOMPurify.sanitize(source) : source;
      window.mermaid.render("mermaid-" + Math.random().toString(36).slice(2), safe)
        .then(function (res) { container.innerHTML = res.svg; })
        .catch(function () { container.textContent = "Mermaid render failed (data pending)."; });
    });
  }

  /* ── Live events panel (WS with reconnect + dedupe + replay) ────────── */
  var feedEl = document.getElementById("event-feed");
  var seenIds = new Set();
  var lastEventTs = null; // ISO timestamp; reconnects pass ?since= for replay

  function addEvent(eventJson) {
    if (!feedEl) return;
    var id = eventJson.id || eventJson.event_id || (eventJson.metadata && eventJson.metadata.event_id);
    if (id && seenIds.has(id)) return; // dedupe replay/live boundary
    if (id) seenIds.add(id);

    var ts = eventJson.timestamp || "";
    if (ts && (!lastEventTs || ts > lastEventTs)) { lastEventTs = ts; }

    var row = document.createElement("div");
    row.className = "event";
    var displayTs = ts.replace("T", " ").slice(0, 19);
    var type = (eventJson.metadata && eventJson.metadata.event_type) || "event";
    if (type.indexOf("error") !== -1 || type.indexOf("failed") !== -1) {
      row.classList.add("error");
    }
    var payload = eventJson.payload || {};
    var summary = typeof payload === "string" ? payload : JSON.stringify(payload).slice(0, 160);
    var safeSummary = window.DOMPurify ? window.DOMPurify.sanitize(summary) : summary;
    var safeType = window.DOMPurify ? window.DOMPurify.sanitize(type) : type;
    var safeTs = window.DOMPurify ? window.DOMPurify.sanitize(displayTs) : displayTs;
    row.innerHTML =
      '<span class="t">' + safeTs + "</span>" +
      '<span class="tag">' + safeType + "</span> " +
      safeSummary;
    feedEl.appendChild(row);
    while (feedEl.children.length > 100) { feedEl.removeChild(feedEl.firstChild); }
  }

  function connectFeed() {
    if (!feedEl) return;
    var url = WS_URL + (lastEventTs ? "?since=" + encodeURIComponent(lastEventTs) : "");
    var ws;
    try { ws = new WebSocket(url); } catch (e) { setTimeout(connectFeed, 3000); return; }
    ws.onmessage = function (msg) {
      var envelope;
      try { envelope = JSON.parse(msg.data); } catch (e) { return; }
      if (envelope.kind === "event") { addEvent(envelope.event); }
    };
    ws.onclose = function () { setTimeout(connectFeed, 3000); };
    ws.onerror = function () { try { ws.close(); } catch (e) { /* noop */ } };
  }

  /* ── Boot ────────────────────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    pollHealth();
    setInterval(pollHealth, POLL_MS);
    setInterval(updateStaleness, 1000);
    renderMarkdown();
    renderMermaid();
    connectFeed();
  });
})();

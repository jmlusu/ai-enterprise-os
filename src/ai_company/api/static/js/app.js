/* AI Enterprise OS — Dashboard client (Phase 1 WS-5.0 + Phase 2 ADR 0010)
   Runs under a strict CSP: no inline scripts, no unsafe-eval.
   Responsibilities:
     - staleness ticker: poll /api/health every N seconds, show age
     - mermaid: render any <pre class="mermaid-source"> block client-side
     - markdown: render [data-md] blocks through marked + DOMPurify
     - events panel: WebSocket feed with auto-reconnect + dedupe
     - write actions: guarded mutations (bearer token + CSRF + audit, ADR 0010)
       with a reason dialog for high-impact actions, plus the Write History
       panel backed by GET /api/audit/writes
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

  /* ── Write actions (Phase 2, ADR 0010: token + CSRF + audit) ────────── */
  var TOKEN_KEY = "aios.write_token";
  var writeStatusEl = document.getElementById("write-status");

  function getWriteToken() {
    try { return window.localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }

  function setWriteToken(value) {
    try {
      if (value) { window.localStorage.setItem(TOKEN_KEY, value); }
      else { window.localStorage.removeItem(TOKEN_KEY); }
    } catch (e) { /* storage unavailable (e.g. private mode): ignore */ }
  }

  function setWriteStatus(text, cls) {
    if (!writeStatusEl) return;
    writeStatusEl.textContent = text;
    writeStatusEl.className = "write-status " + (cls || "");
  }

  async function fetchCsrf() {
    var resp = await fetch("/api/write-csrf", { headers: { "Accept": "application/json" } });
    if (!resp.ok) { throw new Error("CSRF endpoint unavailable (HTTP " + resp.status + ")"); }
    var body = await resp.json();
    if (!body.csrf_token) { throw new Error("CSRF endpoint returned no token"); }
    return body.csrf_token;
  }

  async function performWrite(path, payload) {
    var csrf = await fetchCsrf();
    var headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf };
    var token = getWriteToken();
    if (token) { headers["Authorization"] = "Bearer " + token; }
    var resp = await fetch(path, { method: "POST", headers: headers, body: JSON.stringify(payload || {}) });
    var body = null;
    try { body = await resp.json(); } catch (e) { /* non-JSON body */ }
    if (!resp.ok) {
      var detail = (body && body.detail) || ("HTTP " + resp.status);
      if (resp.status === 401) {
        detail = "Write token missing or invalid — save it on the Write History page.";
      }
      if (resp.status === 403) {
        detail = "CSRF token rejected — refresh the page and retry.";
      }
      throw new Error(detail);
    }
    if (body && body.success === false) {
      throw new Error((body.errors || ["operation failed"]).join("; "));
    }
    return body;
  }

  /* Native <dialog> confirm with an optional required reason (CSP-safe). */
  function openWriteDialog(cfg) {
    return new Promise(function (resolve) {
      var dialog = document.createElement("dialog");
      dialog.className = "write-dialog";
      var prompt = document.createElement("p");
      prompt.textContent = cfg.prompt || "Confirm write action?";
      dialog.appendChild(prompt);

      var reasonBox = null;
      if (cfg.highImpact) {
        var label = document.createElement("label");
        label.className = "write-dialog-label";
        label.textContent = "Reason (required for high-impact actions):";
        dialog.appendChild(label);
        reasonBox = document.createElement("textarea");
        reasonBox.className = "write-dialog-reason";
        reasonBox.placeholder = "e.g. scheduled maintenance window";
        dialog.appendChild(reasonBox);
      }

      var actions = document.createElement("div");
      actions.className = "write-dialog-actions";
      var cancelBtn = document.createElement("button");
      cancelBtn.type = "button"; cancelBtn.className = "btn"; cancelBtn.textContent = "Cancel";
      var confirmBtn = document.createElement("button");
      confirmBtn.type = "button"; confirmBtn.className = "btn btn-danger"; confirmBtn.textContent = "Confirm";
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      dialog.appendChild(actions);

      function closeWith(result) {
        try { dialog.close(); } catch (e) { /* already closed */ }
        if (dialog.parentNode) { dialog.parentNode.removeChild(dialog); }
        resolve(result);
      }
      cancelBtn.addEventListener("click", function () { closeWith(null); });
      confirmBtn.addEventListener("click", function () {
        var reason = reasonBox ? reasonBox.value.trim() : null;
        if (cfg.highImpact && !reason) {
          reasonBox.setAttribute("aria-invalid", "true");
          reasonBox.focus();
          return;
        }
        closeWith(reason);
      });
      dialog.addEventListener("cancel", function () { closeWith(null); });
      document.body.appendChild(dialog);
      dialog.showModal();
      if (reasonBox) { reasonBox.focus(); } else { confirmBtn.focus(); }
    });
  }

  async function runWriteAction(el) {
    var path = el.getAttribute("data-write");
    if (!path || el.disabled) { return; }
    var action = el.getAttribute("data-action") || path;
    var highImpact = el.getAttribute("data-high-impact") === "1";
    var prompt = el.getAttribute("data-prompt") || ("Execute " + action + "?");
    var payload = {};
    var bodyAttr = el.getAttribute("data-body");
    if (bodyAttr) {
      try { payload = JSON.parse(bodyAttr); } catch (e) { payload = { raw: bodyAttr }; }
    }
    if (highImpact) {
      var reason = await openWriteDialog({ prompt: prompt, highImpact: true });
      if (reason === null) { return; } // cancelled
      payload.reason = reason;
    } else if (!window.confirm(prompt)) {
      return;
    }
    el.disabled = true;
    var oldText = el.textContent;
    el.textContent = "running…";
    setWriteStatus("Executing " + action + " …", "info");
    try {
      await performWrite(path, payload);
      setWriteStatus(action + " completed (audited)", "ok");
      if (el.getAttribute("data-reload") === "1") { window.location.reload(); return; }
      loadWriteHistory();
    } catch (err) {
      setWriteStatus(action + " failed: " + err.message, "err");
    } finally {
      el.disabled = false;
      el.textContent = oldText;
    }
  }

  /* ── Write History panel (GET /api/audit/writes, ADR 0010 §3) ───────── */
  var writeHistoryBody = document.getElementById("write-history-tbody");

  function escHtml(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function renderWriteHistoryEmpty(msg) {
    var tr = document.createElement("tr");
    var td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty";
    td.textContent = msg;
    tr.appendChild(td);
    writeHistoryBody.appendChild(tr);
  }

  async function loadWriteHistory() {
    if (!writeHistoryBody) { return; }
    writeHistoryBody.textContent = "";
    var resp;
    try {
      resp = await fetch("/api/audit/writes?limit=50", { headers: { "Accept": "application/json" } });
    } catch (e) {
      renderWriteHistoryEmpty("Network error — write history unavailable.");
      return;
    }
    if (!resp.ok) {
      renderWriteHistoryEmpty("Write history unavailable (HTTP " + resp.status + ").");
      return;
    }
    var body = await resp.json();
    var events = body.events || [];
    if (!events.length) {
      renderWriteHistoryEmpty("No write actions recorded yet.");
      return;
    }
    events.forEach(function (ev) {
      var meta = ev.metadata || {};
      var payload = ev.payload || {};
      var type = meta.event_type || "";
      var ok = type === "audit.write";
      var ts = (meta.timestamp || "").replace("T", " ").slice(0, 19);
      var detail = payload.detail || "";
      if (!detail && payload.details) { detail = JSON.stringify(payload.details); }
      var tr = document.createElement("tr");
      tr.innerHTML =
        '<td class="mono">' + escHtml(ts) + "</td>" +
        '<td><span class="chip ' + (ok ? "ok" : "action") + '">' +
          escHtml(ok ? "write" : "rejected") + "</span></td>" +
        '<td class="mono">' + escHtml(payload.action || "") + "</td>" +
        "<td>" + escHtml(payload.result || (ok ? "ok" : "rejected")) + "</td>" +
        "<td>" + escHtml(payload.reason || "") + "</td>" +
        '<td class="mono">' + escHtml(detail) + "</td>";
      writeHistoryBody.appendChild(tr);
    });
  }

  function wireTokenInput() {
    var input = document.getElementById("write-token-input");
    if (!input) { return; }
    input.value = getWriteToken();
    var saveBtn = document.getElementById("write-token-save");
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        setWriteToken(input.value.trim());
        setWriteStatus(input.value.trim() ? "Write token saved for this browser." : "Write token cleared.", "ok");
      });
    }
    var clearBtn = document.getElementById("write-token-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        input.value = "";
        setWriteToken("");
        setWriteStatus("Write token cleared.", "ok");
      });
    }
  }

  function wireWriteActions() {
    document.addEventListener("click", function (evt) {
      var el = evt.target && evt.target.closest ? evt.target.closest("[data-write]") : null;
      if (!el) { return; }
      evt.preventDefault();
      runWriteAction(el);
    });
  }

  /* ── Boot ────────────────────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    pollHealth();
    setInterval(pollHealth, POLL_MS);
    setInterval(updateStaleness, 1000);
    renderMarkdown();
    renderMermaid();
    connectFeed();
    wireTokenInput();
    wireWriteActions();
    loadWriteHistory();
  });
})();

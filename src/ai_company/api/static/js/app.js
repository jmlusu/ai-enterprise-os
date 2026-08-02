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
        // Canonical four-state vocabulary (R12): ok / watch / action / unknown
        el.textContent = body.status;
        el.className = "chip " + body.status;
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

  /* ── Generate panel (Wave 2b) ───────────────────────────────────────── */
  var generateStatusEl = document.getElementById("generate-status");
  var generateRunsBody = document.getElementById("generate-runs-tbody");
  var generateLogEl = document.getElementById("generate-log");
  var generateTargetSelect = document.getElementById("generate-target");
  var generateTargetDesc = document.getElementById("generate-target-desc");
  var activeRunTimer = null;

  function setGenerateStatus(text, cls) {
    if (!generateStatusEl) return;
    generateStatusEl.textContent = text;
    generateStatusEl.className = "write-status " + (cls || "");
  }

  function wireGenerate() {
    if (!generateTargetSelect) return;
    generateTargetSelect.addEventListener("change", function () {
      var opt = generateTargetSelect.options[generateTargetSelect.selectedIndex];
      if (generateTargetDesc && opt) {
        generateTargetDesc.textContent = opt.dataset.desc || "";
      }
    });
    var dispatchBtn = document.getElementById("generate-dispatch");
    if (dispatchBtn) {
      dispatchBtn.addEventListener("click", async function () {
        var target = generateTargetSelect.value;
        var reason = (document.getElementById("generate-reason") || {}).value || "";
        dispatchBtn.disabled = true;
        setGenerateStatus("Dispatching " + target + " …", "info");
        try {
          var body = await performWrite("/api/generate", { target: target, reason: reason });
          setGenerateStatus("Run " + (body.run ? body.run.run_id : "") + " queued (audited)", "ok");
          loadGenerateRuns();
          scheduleGenerateRefresh();
        } catch (err) {
          setGenerateStatus("Dispatch failed: " + err.message, "err");
        } finally {
          dispatchBtn.disabled = false;
        }
      });
    }
  }

  function runIsActive(run) {
    return run && (run.status === "queued" || run.status === "running");
  }

  function scheduleGenerateRefresh() {
    if (activeRunTimer) { return; }
    activeRunTimer = setInterval(function () {
      loadGenerateRuns().then(function (runs) {
        var anyActive = runs.some(runIsActive);
        if (!anyActive) {
          clearInterval(activeRunTimer);
          activeRunTimer = null;
        }
      });
    }, 3000);
  }

  function escAttr(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function generateStatusClass(status) {
    if (status === "succeeded") { return "ok"; }
    if (status === "failed") { return "action"; }
    if (status === "cancelled") { return "watch"; }
    return "watch"; // queued / running
  }

  async function loadGenerateRuns() {
    if (!generateRunsBody) { return []; }
    var runs = [];
    try {
      var resp = await fetch("/api/generate/runs?limit=25", { headers: { "Accept": "application/json" } });
      if (resp.ok) {
        var body = await resp.json();
        runs = body.runs || [];
      }
    } catch (e) { /* keep last render */ }
    generateRunsBody.textContent = "";
    if (!runs.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 7;
      td.className = "empty";
      td.textContent = "No generation runs yet.";
      tr.appendChild(td);
      generateRunsBody.appendChild(tr);
      return runs;
    }
    runs.forEach(function (run) {
      var tr = document.createElement("tr");
      var ts = function (v) { return (v || "").replace("T", " ").slice(0, 19); };
      var logBtn = document.createElement("button");
      logBtn.type = "button"; logBtn.className = "btn btn-sm";
      logBtn.textContent = "Log";
      logBtn.addEventListener("click", function () { showGenerateLog(run.run_id); });
      var cancelBtn = null;
      if (runIsActive(run)) {
        cancelBtn = document.createElement("button");
        cancelBtn.type = "button"; cancelBtn.className = "btn btn-sm btn-danger";
        cancelBtn.textContent = "Cancel";
        cancelBtn.addEventListener("click", async function () {
          try {
            await performWrite("/api/generate/" + run.run_id + "/cancel", {});
            setGenerateStatus("Cancelled " + run.run_id + " (audited)", "ok");
            loadGenerateRuns();
          } catch (err) {
            setGenerateStatus("Cancel failed: " + err.message, "err");
          }
        });
      }
      var actions = document.createElement("span");
      actions.className = "write-actions inline";
      actions.appendChild(logBtn);
      if (cancelBtn) { actions.appendChild(cancelBtn); }
      tr.innerHTML =
        '<td class="mono">' + escAttr(run.run_id) + "</td>" +
        "<td>" + escAttr(run.target) + "</td>" +
        '<td><span class="chip ' + generateStatusClass(run.status) + '">' + escAttr(run.status) + "</span></td>" +
        "<td>" + escAttr(ts(run.started_at)) + "</td>" +
        "<td>" + escAttr(ts(run.finished_at)) + "</td>" +
        "<td>" + escAttr(run.exit_code == null ? "—" : run.exit_code) + "</td>";
      var tdActions = document.createElement("td");
      tdActions.appendChild(actions);
      tr.appendChild(tdActions);
      generateRunsBody.appendChild(tr);
      if (run.error) {
        var trErr = document.createElement("tr");
        var tdErr = document.createElement("td");
        tdErr.colSpan = 7;
        tdErr.className = "mono error-text";
        tdErr.textContent = run.error;
        trErr.appendChild(tdErr);
        generateRunsBody.appendChild(trErr);
      }
    });
    if (runs.some(runIsActive)) { scheduleGenerateRefresh(); }
    return runs;
  }

  async function showGenerateLog(runId) {
    if (!generateLogEl) { return; }
    generateLogEl.textContent = "Loading log for " + runId + " …";
    try {
      var resp = await fetch("/api/generate/runs/" + runId + "/log?max_lines=500", { headers: { "Accept": "application/json" } });
      if (!resp.ok) {
        generateLogEl.textContent = "Log unavailable (HTTP " + resp.status + ").";
        return;
      }
      var body = await resp.json();
      var lines = body.lines || [];
      generateLogEl.textContent = lines.length
        ? lines.join("\n")
        : "Run has no log output yet (still starting, or output was empty).";
      generateLogEl.scrollTop = generateLogEl.scrollHeight;
    } catch (e) {
      generateLogEl.textContent = "Log unavailable (network error).";
    }
  }

  /* ── Decision inbox (Wave 2b) ───────────────────────────────────────── */
  var decisionStatusEl = document.getElementById("decision-status");

  function setDecisionStatus(text, cls) {
    if (!decisionStatusEl) return;
    decisionStatusEl.textContent = text;
    decisionStatusEl.className = "write-status " + (cls || "");
  }

  function decisionDialog(titleText, fields) {
    /* fields: [{key, label, type: 'text'|'select'|'textarea', required, options}] */
    return new Promise(function (resolve) {
      var dialog = document.createElement("dialog");
      dialog.className = "write-dialog";
      var title = document.createElement("p");
      title.textContent = titleText;
      dialog.appendChild(title);
      var inputs = {};
      fields.forEach(function (field) {
        var label = document.createElement("label");
        label.className = "write-dialog-label";
        label.textContent = field.label + (field.required ? " (required)" : "");
        dialog.appendChild(label);
        var input;
        if (field.type === "select") {
          input = document.createElement("select");
          (field.options || []).forEach(function (opt) {
            var option = document.createElement("option");
            option.value = opt.value;
            option.textContent = opt.label;
            input.appendChild(option);
          });
        } else if (field.type === "textarea") {
          input = document.createElement("textarea");
          input.className = "write-dialog-reason";
          input.placeholder = field.placeholder || "";
        } else {
          input = document.createElement("input");
          input.type = "text";
          input.className = "write-dialog-reason";
          input.placeholder = field.placeholder || "";
        }
        dialog.appendChild(input);
        inputs[field.key] = input;
      });
      var actions = document.createElement("div");
      actions.className = "write-dialog-actions";
      var cancelBtn = document.createElement("button");
      cancelBtn.type = "button"; cancelBtn.className = "btn"; cancelBtn.textContent = "Cancel";
      var confirmBtn = document.createElement("button");
      confirmBtn.type = "button"; confirmBtn.className = "btn btn-danger"; confirmBtn.textContent = "Confirm";
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      dialog.appendChild(actions);
      function closeWith(value) {
        try { dialog.close(); } catch (e) { /* already closed */ }
        if (dialog.parentNode) { dialog.parentNode.removeChild(dialog); }
        resolve(value);
      }
      cancelBtn.addEventListener("click", function () { closeWith(null); });
      confirmBtn.addEventListener("click", function () {
        var result = {};
        var valid = true;
        fields.forEach(function (field) {
          var value = inputs[field.key].value.trim();
          if (field.required && !value) {
            inputs[field.key].setAttribute("aria-invalid", "true");
            valid = false;
          }
          result[field.key] = value;
        });
        if (!valid) { return; }
        closeWith(result);
      });
      dialog.addEventListener("cancel", function () { closeWith(null); });
      document.body.appendChild(dialog);
      dialog.showModal();
      confirmBtn.focus();
    });
  }

  async function createDecision() {
    var titleEl = document.getElementById("decision-title");
    var descEl = document.getElementById("decision-description");
    var catEl = document.getElementById("decision-category");
    var prioEl = document.getElementById("decision-priority");
    var optsEl = document.getElementById("decision-options");
    var title = titleEl.value.trim();
    var description = descEl.value.trim();
    if (!title || !description) {
      setDecisionStatus("Title and description are required.", "err");
      return;
    }
    var options = [];
    optsEl.value.split("\n").forEach(function (line, idx) {
      line = line.trim();
      if (!line) { return; }
      var parts = line.split(/\s*—\s*|\s*-\s*/, 2);
      options.push({
        id: "opt" + (idx + 1),
        label: parts[0].trim(),
        description: (parts[1] || "").trim()
      });
    });
    try {
      var body = await performWrite("/api/decisions", {
        title: title,
        description: description,
        category: catEl.value,
        priority: prioEl.value,
        requester: "dashboard",
        options: options
      });
      setDecisionStatus("Decision " + (body.decision ? body.decision.id : "") + " created (audited)", "ok");
      titleEl.value = ""; descEl.value = ""; optsEl.value = "";
      setTimeout(function () { window.location.reload(); }, 800);
    } catch (err) {
      setDecisionStatus("Create failed: " + err.message, "err");
    }
  }

  function decisionOptions(card) {
    var options = [];
    var rows = card.querySelectorAll("tbody tr");
    rows.forEach(function (row) {
      var cells = row.querySelectorAll("td");
      if (cells.length >= 2) {
        options.push({ value: cells[0].textContent.trim(), label: cells[0].textContent.trim() });
      }
    });
    return options;
  }

  async function decisionAction(action, card) {
    var decisionId = card.getAttribute("data-decision-id");
    var payload;
    if (action === "approve") {
      var opts = decisionOptions(card);
      if (!opts.length) {
        setDecisionStatus("This decision has no options to approve.", "err");
        return;
      }
      var res = await decisionDialog("Approve " + decisionId, [
        { key: "selected_option", label: "Option", type: "select", required: true, options: opts },
        { key: "rationale", label: "Rationale", type: "textarea", required: true },
        { key: "approved_by", label: "Approved by", type: "text", required: true, placeholder: "dashboard-operator" }
      ]);
      if (!res) { return; }
      payload = { selected_option: res.selected_option, rationale: res.rationale, approved_by: res.approved_by || "dashboard-operator" };
    } else if (action === "reject" || action === "cancel") {
      var res = await decisionDialog((action === "reject" ? "Reject " : "Cancel ") + decisionId, [
        { key: "reason", label: "Reason", type: "textarea", required: true }
      ]);
      if (!res) { return; }
      payload = { reason: res.reason };
    } else { // escalate
      var res = await decisionDialog("Escalate " + decisionId, [
        { key: "note", label: "Escalation note", type: "textarea", required: false }
      ]);
      if (!res) { return; }
      payload = { note: res.note };
    }
    try {
      await performWrite("/api/decisions/" + decisionId + "/" + action, payload);
      setDecisionStatus(decisionId + " → " + action + " (audited)", "ok");
      setTimeout(function () { window.location.reload(); }, 800);
    } catch (err) {
      setDecisionStatus(action + " failed: " + err.message, "err");
    }
  }

  function wireDecisionActions() {
    var createBtn = document.getElementById("decision-create");
    if (createBtn) { createBtn.addEventListener("click", createDecision); }
    document.addEventListener("click", function (evt) {
      var btn = evt.target && evt.target.closest ? evt.target.closest("[data-decision-approve], [data-decision-reject], [data-decision-escalate], [data-decision-cancel]") : null;
      if (!btn) { return; }
      evt.preventDefault();
      var card = btn.closest(".decision-card");
      if (!card) { return; }
      var action = btn.hasAttribute("data-decision-approve") ? "approve"
        : btn.hasAttribute("data-decision-reject") ? "reject"
        : btn.hasAttribute("data-decision-escalate") ? "escalate" : "cancel";
      decisionAction(action, card);
    });
  }

  /* ── Backup tile age (R6) ────────────────────────────────────────────── */
  function updateBackupAge() {
    var el = document.getElementById("backup-age");
    if (!el) { return; }
    var latest = el.getAttribute("data-latest") || "";
    if (!latest) {
      el.textContent = "none";
      el.className = "mono chip action";
      return;
    }
    var modified = new Date(latest).getTime();
    if (isNaN(modified)) { return; }
    var hours = Math.max(0, Math.floor((Date.now() - modified) / 3600000));
    var text = hours < 1
      ? Math.max(0, Math.floor((Date.now() - modified) / 60000)) + "m ago"
      : hours + "h ago";
    el.textContent = text;
    el.className = "mono chip " + (hours > 48 ? "watch" : "ok");
  }

  /* ── Write actions (Phase 2, ADR 0010: token + CSRF + audit) ────────── */
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
    wireGenerate();
    loadGenerateRuns();
    wireDecisionActions();
    updateBackupAge();
    setInterval(updateBackupAge, 30000);
  });
})();

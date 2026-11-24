// 1) Adds a "Create account" link under Chainlit's login form.
// 2) Swaps the composer's Send button for a Stop button while a study session is running and the box is empty.
//    Chainlit's own Stop only shows while the app is computing, not while it waits for an answer,
//    so this one calls POST /stop-session to end the whole study session.
(function () {
  function addLink() {
    if (!location.pathname.endsWith("/login") || document.getElementById("register-link")) return;
    var form = document.querySelector("form");
    if (!form) return;
    var a = document.createElement("a");
    a.id = "register-link";
    a.href = "/register";
    a.textContent = "Create account";
    a.style.cssText = "display:block;text-align:center;margin-top:1rem;font-size:.9rem;text-decoration:underline";
    form.parentNode.appendChild(a);
  }

  var STOP_ID = "stop-session-btn";
  var SQUARE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';

  var active = false;

  function poll() {
    fetch("/session-active", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { active: false }; })
      .then(function (j) { if (j.active !== active) { active = !!j.active; syncStop(); } })
      .catch(function () {});
  }

  function inputEmpty() {
    var input = document.getElementById("chat-input");
    return !input || (input.textContent || input.value || "").trim() === "";
  }

  // Chainlit shows its own Stop only while it is computing and Send otherwise; either way we replace it with ours
  // whenever the message box is empty, so the same Stop (which ends the whole session) is always visible.
  function syncStop() {
    var target = document.getElementById("chat-submit") || document.getElementById("stop-button");
    var stop = document.getElementById(STOP_ID);
    if (!target) {
      if (stop) stop.remove();
      return;
    }
    if (active && inputEmpty()) {
      ["chat-submit", "stop-button"].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = "none";
      });
      if (!stop || stop.nextSibling !== target) {
        if (stop) stop.remove();
        stop = document.createElement("button");
        stop.id = STOP_ID;
        stop.type = "button";
        stop.className = target.className;
        stop.title = "Stop the current session and start a new topic";
        stop.innerHTML = SQUARE;
        stop.addEventListener("click", function () {
          fetch("/stop-session", { method: "POST", credentials: "same-origin" }).then(poll).catch(function () {});
        });
        target.parentNode.insertBefore(stop, target);
      }
    } else {
      ["chat-submit", "stop-button"].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = "";
      });
      if (stop) stop.remove();
    }
  }

  // "Logs" button: shows this user's recent server log lines (GET /session-logs) in a panel.
  var LOGS_BTN = "logs-btn", LOGS_PANEL = "logs-panel", logsTimer = null;

  function loadLogs() {
    var pre = document.getElementById("logs-text");
    if (!pre) return;
    fetch("/session-logs", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
        pre.textContent = j.lines.length ? j.lines.join("\n") : "No log lines yet. Start a study goal and they will appear here.";
        if (atEnd) pre.scrollTop = pre.scrollHeight;
      })
      .catch(function () { pre.textContent = "Could not load logs."; });
  }

  function closeLogs() {
    var panel = document.getElementById(LOGS_PANEL);
    if (panel) panel.remove();
    clearInterval(logsTimer);
  }

  function openLogs() {
    if (document.getElementById(LOGS_PANEL)) return closeLogs();
    var panel = document.createElement("div");
    panel.id = LOGS_PANEL;
    panel.style.cssText = "position:fixed;right:16px;bottom:72px;width:min(720px,calc(100vw - 32px));height:50vh;z-index:60;display:flex;flex-direction:column;border-radius:8px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.35);background:#0f1117;color:#d6d9e0;font:12px/1.5 ui-monospace,Menlo,monospace";
    panel.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#1b1e27;font:600 13px system-ui"><span>Session logs</span><span><button id="logs-refresh" style="margin-right:12px">Refresh</button><button id="logs-close">Close</button></span></div><pre id="logs-text" style="flex:1;margin:0;padding:10px 12px;overflow:auto;white-space:pre-wrap"></pre>';
    document.body.appendChild(panel);
    document.getElementById("logs-close").onclick = closeLogs;
    document.getElementById("logs-refresh").onclick = loadLogs;
    loadLogs();
    logsTimer = setInterval(loadLogs, 3000);
  }

  function syncLogsButton() {
    var show = !location.pathname.endsWith("/login") && !location.pathname.endsWith("/register") && document.getElementById("chat-input");
    var btn = document.getElementById(LOGS_BTN);
    if (!show) { if (btn) btn.remove(); return; }
    if (btn) return;
    btn = document.createElement("button");
    btn.id = LOGS_BTN;
    btn.type = "button";
    btn.textContent = "Logs";
    btn.title = "Show the logs of your sessions";
    btn.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:55;padding:6px 14px;border-radius:999px;border:1px solid rgba(128,128,128,.4);background:rgba(128,128,128,.15);cursor:pointer;font:600 12px system-ui;color:inherit";
    btn.onclick = openLogs;
    document.body.appendChild(btn);
  }

  function update() {
    syncLogsButton();
    addLink();
    syncStop();
  }

  new MutationObserver(update).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  document.addEventListener("input", syncStop, true);
  setInterval(poll, 1500);
  update();
})();

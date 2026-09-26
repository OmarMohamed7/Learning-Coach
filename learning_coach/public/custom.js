// 1) Adds a "Create account" link under Chainlit's login form.
// 2) Swaps the composer's Send button for a Stop button while the message box is empty.
//    Chainlit's own Stop only shows while the app is computing, not while it waits for an answer,
//    so this one calls POST /stop-session to end the whole study session (roadmap and topic).
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
    if (inputEmpty()) {
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
          fetch("/stop-session", { method: "POST", credentials: "same-origin" }).catch(function () {});
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

  function update() {
    addLink();
    syncStop();
  }

  new MutationObserver(update).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  document.addEventListener("input", syncStop, true);
  update();
})();

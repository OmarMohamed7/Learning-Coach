// Adds a "Create account" link under Chainlit's login form.
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
  new MutationObserver(addLink).observe(document.documentElement, { childList: true, subtree: true });
  addLink();
})();

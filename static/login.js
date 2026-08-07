(function () {
  "use strict";
  var form = document.getElementById("loginForm");
  var msg = document.getElementById("msg");
  var btn = document.getElementById("submitBtn");

  function show(text, kind) {
    msg.innerHTML = '<div class="notice ' + kind + '">' + text + "</div>";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    btn.disabled = true;
    var username = document.getElementById("username").value.trim();
    var password = document.getElementById("password").value;

    fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username, password: password }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, j: j }; });
      })
      .then(function (res) {
        if (res.ok && res.j.ok) {
          window.location.href = "/admin";
        } else {
          show(res.j.detail || "შესვლა ვერ მოხერხდა.", "bad");
          btn.disabled = false;
        }
      })
      .catch(function () {
        show("კავშირის შეცდომა.", "bad");
        btn.disabled = false;
      });
  });
})();

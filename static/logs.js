/* Tap log: every card tap at the kiosk, allowed AND denied.
 *
 * Denied taps are recorded nowhere else — `scans` only holds granted meals —
 * so this page is the only place a turned-away person is visible afterwards.
 */
(function () {
  "use strict";

  var els = {
    userLabel: document.getElementById("userLabel"),
    logoutBtn: document.getElementById("logoutBtn"),
    logFrom: document.getElementById("logFrom"),
    logTo: document.getElementById("logTo"),
    logBtn: document.getElementById("logBtn"),
    logStats: document.getElementById("logStats"),
    logMsg: document.getElementById("logMsg"),
    logStatusChips: document.getElementById("logStatusChips"),
    logSearch: document.getElementById("logSearch"),
    logBody: document.getElementById("logBody"),
    logCount: document.getElementById("logCount"),
    logXlsx: document.getElementById("logXlsx"),
    logCsv: document.getElementById("logCsv"),
    logXlsxCc: document.getElementById("logXlsxCc"),
  };

  var logStatus = "";   // "" | "ALLOWED" | "DENIED"
  var logRows = [];     // last fetch; the search box filters this client-side

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function iso(d) {
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  function api(url) {
    return fetch(url).then(function (r) {
      if (r.status === 401) { window.location.href = "/login"; throw new Error("auth"); }
      return r.json();
    });
  }

  function renderStats(d) {
    els.logStats.innerHTML =
      '<div class="stat"><div class="stat-num">' + d.total + "</div>" +
        '<div class="stat-label">სულ მიდება</div></div>' +
      '<div class="stat"><div class="stat-num" style="color:var(--ok)">' + d.allowed + "</div>" +
        '<div class="stat-label">ნებადართული</div></div>' +
      '<div class="stat"><div class="stat-num" style="color:var(--danger)">' + d.denied + "</div>" +
        '<div class="stat-label">უარყოფილი</div></div>';

    if (d.by_reason && d.by_reason.length) {
      var reasons = d.by_reason.map(function (r) {
        return '<span class="badge off" style="margin-inline-end:6px">' +
          esc(r.reason) + ": " + r.count + "</span>";
      }).join(" ");
      els.logMsg.innerHTML =
        '<div style="margin-top:10px;color:var(--muted)">უარყოფის მიზეზები: ' +
        reasons + "</div>";
    } else {
      els.logMsg.innerHTML = "";
    }
  }

  function renderRows() {
    var q = (els.logSearch.value || "").trim().toLowerCase();
    var list = logRows.filter(function (r) {
      if (!q) return true;
      return ((r.full_name || "") + " " + (r.cc_code || "") + " " + r.card_id)
        .toLowerCase().indexOf(q) !== -1;
    });
    els.logCount.textContent = "ნაჩვენებია: " + list.length;
    els.logBody.innerHTML = list.map(function (r) {
      var ok = r.status === "ALLOWED";
      var badge = '<span class="badge ' + (ok ? "ok" : "off") + '">' +
        esc(r.status_ka) + "</span>";
      var name = r.full_name ? esc(r.full_name)
                             : '<span style="color:var(--muted)">—</span>';
      return "<tr>" +
        '<td class="ltr mono">' + esc(r.date) + " " + esc(r.time) + "</td>" +
        "<td>" + name + "</td>" +
        '<td class="ltr mono">' + esc(r.cc_code || "") + "</td>" +
        '<td class="ltr mono">' + esc(r.card_id) + "</td>" +
        "<td>" + badge + "</td>" +
        '<td style="color:var(--muted)">' + esc(r.reason || "") + "</td>" +
        '<td>' + (r.mistaken ? '<span class="badge off">შეცდომით დაფიქსირებული</span>' :
          '<button class="small ghost" data-mistaken="' + r.id + '">შეცდომით დაფიქსირდა</button>') + '</td>' +
        "</tr>";
    }).join("") ||
      '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:22px">ჩანაწერი არ არის</td></tr>';
  }

  function load() {
    var f = els.logFrom.value, t = els.logTo.value;
    if (!f || !t) return;
    if (f > t) {
      els.logMsg.innerHTML =
        '<div class="notice bad">საწყისი თარიღი ბოლოზე გვიანია.</div>';
      return;
    }
    var url = "/api/reports/taplog?from=" + f + "&to=" + t +
      (logStatus ? "&status=" + logStatus : "");
    api(url).then(function (d) {
      renderStats(d);
      logRows = d.rows || [];
      renderRows();
    });
  }

  function download(format, includePos) {
    var f = els.logFrom.value, t = els.logTo.value;
    if (!f || !t) return;
    var url = "/api/reports/taplog-export?from=" + f + "&to=" + t +
      "&format=" + format + (logStatus ? "&status=" + logStatus : "");
    if (includePos === false) url += "&pos=0";
    window.location.href = url;
  }

  function setRange(kind) {
    var now = new Date();
    var from = new Date(now), to = new Date(now);
    if (kind === "week") {
      var day = (now.getDay() + 6) % 7;     // 0 = Monday
      from.setDate(now.getDate() - day);
    } else if (kind === "month") {
      from = new Date(now.getFullYear(), now.getMonth(), 1);
    }
    els.logFrom.value = iso(from);
    els.logTo.value = iso(to);
    load();
  }

  els.logBody.addEventListener("click", function (e) {
    var button = e.target.closest("button[data-mistaken]");
    if (!button) return;
    if (!confirm("მოინიშნოს შეცდომით დაფიქსირებულად? შესაბამისი კვება აღარ ჩაითვლება, ჩანაწერი კი ლოგში დარჩება.")) return;
    button.disabled = true;
    fetch("/api/reports/taplog/" + button.dataset.mistaken + "/mistaken", { method: "POST" })
      .then(function (r) { if (!r.ok) throw new Error(); return load(); })
      .catch(function () { els.logMsg.textContent = "შენახვა ვერ მოხერხდა. სცადეთ ხელახლა."; button.disabled = false; });
  });

  // Wire up
  els.logBtn.addEventListener("click", load);
  els.logSearch.addEventListener("input", renderRows);
  document.querySelectorAll("button[data-range]").forEach(function (b) {
    b.addEventListener("click", function () { setRange(b.dataset.range); });
  });
  els.logStatusChips.addEventListener("click", function (e) {
    var chip = e.target.closest("button.chip");
    if (!chip) return;
    logStatus = chip.dataset.status || "";
    Array.prototype.forEach.call(
      els.logStatusChips.querySelectorAll(".chip"),
      function (c) { c.classList.toggle("active", c === chip); });
    load();
  });
  els.logXlsx.addEventListener("click", function () { download("xlsx"); });
  els.logCsv.addEventListener("click", function () { download("csv"); });
  els.logXlsxCc.addEventListener("click", function () { download("xlsx", false); });
  els.logoutBtn.addEventListener("click", function () {
    fetch("/api/logout", { method: "POST" })
      .then(function () { window.location.href = "/login"; });
  });

  // Init: today, so the page is useful the moment it opens.
  fetch("/api/me").then(function (r) {
    if (r.status === 401) { window.location.href = "/login"; return; }
    return r.json();
  }).then(function (me) {
    if (me && me.username) els.userLabel.textContent = me.username;
    var today = iso(new Date());
    els.logFrom.value = today;
    els.logTo.value = today;
    load();
  });
})();

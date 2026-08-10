/* Reports: today summary, daily counts, day detail, and file downloads. */
(function () {
  "use strict";

  var els = {
    userLabel: document.getElementById("userLabel"),
    logoutBtn: document.getElementById("logoutBtn"),
    statAte: document.getElementById("statAte"),
    statMeals: document.getElementById("statMeals"),
    statActive: document.getElementById("statActive"),
    statRemaining: document.getElementById("statRemaining"),
    todayDate: document.getElementById("todayDate"),
    fromDate: document.getElementById("fromDate"),
    toDate: document.getElementById("toDate"),
    applyBtn: document.getElementById("applyBtn"),
    rangeMsg: document.getElementById("rangeMsg"),
    dailyBody: document.getElementById("dailyBody"),
    dayDate: document.getElementById("dayDate"),
    dayBtn: document.getElementById("dayBtn"),
    dayCount: document.getElementById("dayCount"),
    dayBody: document.getElementById("dayBody"),
    attXlsx: document.getElementById("attXlsx"),
    attCsv: document.getElementById("attCsv"),
    detXlsx: document.getElementById("detXlsx"),
    detCsv: document.getElementById("detCsv"),
    detXlsxCc: document.getElementById("detXlsxCc"),
    detCsvCc: document.getElementById("detCsvCc"),
  };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function notice(text, kind) {
    els.rangeMsg.innerHTML = text ? '<div class="notice ' + kind + '">' + text + "</div>" : "";
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

  function loadToday() {
    api("/api/reports/today").then(function (t) {
      els.statAte.textContent = (t.people_ate != null ? t.people_ate : t.ate);
      if (els.statMeals) els.statMeals.textContent = (t.meals != null ? t.meals : t.ate);
      els.statActive.textContent = t.active;
      els.statRemaining.textContent = t.remaining;
      els.todayDate.textContent = "თარიღი: " + t.date;
    });
  }

  function loadDaily() {
    var f = els.fromDate.value, t = els.toDate.value;
    if (!f || !t) return;
    if (f > t) { notice("საწყისი თარიღი ბოლოზე გვიანია.", "bad"); return; }
    notice("", "");
    api("/api/reports/daily?from=" + f + "&to=" + t).then(function (res) {
      els.dailyBody.innerHTML = (res.rows || []).map(function (r) {
        return '<tr><td class="ltr">' + esc(r.date) + "</td><td>" + r.count + "</td></tr>";
      }).join("") || '<tr><td colspan="2" style="text-align:center;color:var(--muted)">მონაცემი არ არის</td></tr>';
    });
  }

  function loadDay() {
    var d = els.dayDate.value;
    if (!d) return;
    var url = "/api/reports/day?date=" + d;
    api(url).then(function (res) {
      var people = res.people != null ? res.people : (res.rows || []).length;
      var meals = res.meals != null ? res.meals : people;
      els.dayCount.textContent = "კაცი: " + people + "  •  კვება: " + meals;
      els.dayBody.innerHTML = (res.rows || []).map(function (r) {
        var times = (r.times || (r.time ? [r.time] : [])).join(", ");
        var countBadge = '<span class="badge ' + (r.count > 1 ? "warn-badge" : "ok") + '">' + r.count + "</span>";
        var name = r.full_name
          ? esc(r.full_name)
          : '<span style="color:var(--muted)">—</span>';
        return "<tr><td>" + name + "</td>" +
               '<td class="ltr mono">' + esc(r.cc_code || "") + "</td>" +
               '<td class="ltr mono">' + esc(r.card_id) + "</td>" +
               "<td>" + countBadge + '</td><td class="ltr">' + esc(times) + "</td></tr>";
      }).join("") || '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:18px">ამ დღეს არავის უჭამია</td></tr>';
    });
  }

  // includePos=false asks for the Coca-Cola-only sheet (no POS card id).
  function download(kind, format, includePos) {
    var f = els.fromDate.value, t = els.toDate.value;
    if (!f || !t) { notice("აირჩიეთ პერიოდი.", "warn"); return; }
    if (f > t) { notice("საწყისი თარიღი ბოლოზე გვიანია.", "bad"); return; }
    var ep = kind === "attendance" ? "attendance" : "export";
    var url = "/api/reports/" + ep + "?from=" + f + "&to=" + t + "&format=" + format;
    if (kind === "detail" && includePos === false) url += "&pos=0";
    window.location.href = url;
  }

  // Quick ranges
  function setRange(kind) {
    var now = new Date();
    var from = new Date(now), to = new Date(now);
    if (kind === "week") {
      // ISO-ish week: Monday..today
      var day = (now.getDay() + 6) % 7; // 0 = Monday
      from.setDate(now.getDate() - day);
    } else if (kind === "month") {
      from = new Date(now.getFullYear(), now.getMonth(), 1);
    }
    els.fromDate.value = iso(from);
    els.toDate.value = iso(to);
    loadDaily();
  }

  // Wire up
  els.applyBtn.addEventListener("click", function () { loadDaily(); });
  els.dayBtn.addEventListener("click", loadDay);
  els.dayDate.addEventListener("keydown", function (e) { if (e.key === "Enter") loadDay(); });
  document.querySelectorAll("button[data-range]").forEach(function (b) {
    b.addEventListener("click", function () { setRange(b.dataset.range); });
  });
  els.attXlsx.addEventListener("click", function () { download("attendance", "xlsx"); });
  els.attCsv.addEventListener("click", function () { download("attendance", "csv"); });
  els.detXlsx.addEventListener("click", function () { download("detail", "xlsx"); });
  els.detCsv.addEventListener("click", function () { download("detail", "csv"); });
  if (els.detXlsxCc) els.detXlsxCc.addEventListener("click", function () { download("detail", "xlsx", false); });
  if (els.detCsvCc) els.detCsvCc.addEventListener("click", function () { download("detail", "csv", false); });

  els.logoutBtn.addEventListener("click", function () {
    fetch("/api/logout", { method: "POST" }).then(function () { window.location.href = "/login"; });
  });

  // Init
  fetch("/api/me").then(function (r) {
    if (r.status === 401) { window.location.href = "/login"; return; }
    return r.json();
  }).then(function (me) {
    if (me && me.username) els.userLabel.textContent = me.username;
    var today = iso(new Date());
    els.fromDate.value = today;
    els.toDate.value = today;
    els.dayDate.value = today;
    loadToday();
    loadDaily();
    loadDay();
  });
})();

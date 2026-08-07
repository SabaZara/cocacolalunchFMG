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
    quantBody: document.getElementById("quantBody"),
    quantFoot: document.getElementById("quantFoot"),
    quantPeriod: document.getElementById("quantPeriod"),
    quantXlsx: document.getElementById("quantXlsx"),
    quantCsv: document.getElementById("quantCsv"),
    dayWindowChips: document.getElementById("dayWindowChips"),
    mealSplit: document.getElementById("mealSplit"),
    mealSplitSave: document.getElementById("mealSplitSave"),
    mealSplitMsg: document.getElementById("mealSplitMsg"),
  };

  // current day-detail meal-window filter: "" | "1" | "2"
  var dayWindow = "";

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
    var url = "/api/reports/day?date=" + d + (dayWindow ? "&window=" + dayWindow : "");
    api(url).then(function (res) {
      var people = res.people != null ? res.people : (res.rows || []).length;
      var meals = res.meals != null ? res.meals : people;
      var extra = "";
      if (res.w1 != null && res.w2 != null) {
        extra = "  •  პირველი: " + res.w1 + "  •  მეორე: " + res.w2;
      }
      els.dayCount.textContent = "კაცი: " + people + "  •  კვება: " + meals + extra;
      els.dayBody.innerHTML = (res.rows || []).map(function (r) {
        var times = (r.times || (r.time ? [r.time] : [])).join(", ");
        var countBadge = '<span class="badge ' + (r.count > 1 ? "warn-badge" : "ok") + '">' + r.count + "</span>";
        return '<tr><td class="ltr mono">' + esc(r.card_id) + "</td>" +
               "<td>" + countBadge + '</td><td class="ltr">' + esc(times) + "</td></tr>";
      }).join("") || '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:18px">ამ დღეს არავის უჭამია</td></tr>';
    });
  }

  function loadQuant() {
    var f = els.fromDate.value, t = els.toDate.value;
    if (!f || !t || f > t) return;
    api("/api/reports/quant?from=" + f + "&to=" + t).then(function (res) {
      els.quantPeriod.textContent = "პერიოდი: " + res.from + " — " + res.to +
        "  (" + res.windows.meal1 + " / " + res.windows.meal2 + ")";
      els.quantBody.innerHTML = (res.rows || []).map(function (r) {
        return '<tr><td class="ltr">' + esc(r.date) + "</td><td>" + r.meal1 +
               "</td><td>" + r.meal2 + '</td><td style="font-weight:700">' + r.total + "</td></tr>";
      }).join("") || '<tr><td colspan="4" style="text-align:center;color:var(--muted)">მონაცემი არ არის</td></tr>';
      var g = res.grand || {meal1: 0, meal2: 0, total: 0};
      els.quantFoot.innerHTML =
        '<tr style="font-weight:800;background:#f1f5fa">' +
        "<td>ჯამი</td><td>" + g.meal1 + "</td><td>" + g.meal2 +
        "</td><td>" + g.total + "</td></tr>";
    });
  }

  function download(kind, format) {
    var f = els.fromDate.value, t = els.toDate.value;
    if (!f || !t) { notice("აირჩიეთ პერიოდი.", "warn"); return; }
    if (f > t) { notice("საწყისი თარიღი ბოლოზე გვიანია.", "bad"); return; }
    var ep = kind === "attendance" ? "attendance" : "export";
    window.location.href = "/api/reports/" + ep + "?from=" + f + "&to=" + t + "&format=" + format;
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
    loadQuant();
  }

  function downloadQuant(format) {
    var f = els.fromDate.value, t = els.toDate.value;
    if (!f || !t) { notice("აირჩიეთ პერიოდი.", "warn"); return; }
    if (f > t) { notice("საწყისი თარიღი ბოლოზე გვიანია.", "bad"); return; }
    window.location.href = "/api/reports/quant-export?from=" + f + "&to=" + t + "&format=" + format;
  }

  // Wire up
  els.applyBtn.addEventListener("click", function () { loadDaily(); loadQuant(); });
  els.dayBtn.addEventListener("click", loadDay);
  els.dayDate.addEventListener("keydown", function (e) { if (e.key === "Enter") loadDay(); });
  document.querySelectorAll("button[data-range]").forEach(function (b) {
    b.addEventListener("click", function () { setRange(b.dataset.range); });
  });
  els.attXlsx.addEventListener("click", function () { download("attendance", "xlsx"); });
  els.attCsv.addEventListener("click", function () { download("attendance", "csv"); });
  els.detXlsx.addEventListener("click", function () { download("detail", "xlsx"); });
  els.detCsv.addEventListener("click", function () { download("detail", "csv"); });
  els.quantXlsx.addEventListener("click", function () { downloadQuant("xlsx"); });
  els.quantCsv.addEventListener("click", function () { downloadQuant("csv"); });

  function loadMealSplit() {
    api("/api/settings").then(function (s) {
      if (s && s.meal_split) els.mealSplit.value = s.meal_split;
    });
  }
  els.mealSplitSave.addEventListener("click", function () {
    var v = els.mealSplit.value;
    if (!v) { els.mealSplitMsg.textContent = "მიუთითეთ დრო."; return; }
    if (!confirm("გაყოფის დროის შეცვლა " + v + "-ზე? რეპორტი თავიდან დაითვლება.")) return;
    els.mealSplitSave.disabled = true;
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
      body: JSON.stringify({ meal_split: v }),
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, j: j }; });
    }).then(function (res) {
      if (res.ok) {
        els.mealSplitMsg.textContent = "შენახულია ✓";
        loadQuant(); loadDay();
      } else {
        els.mealSplitMsg.textContent = (res.j && res.j.detail) || "ვერ შეინახა.";
      }
    }).catch(function () { els.mealSplitMsg.textContent = "ვერ შეინახა."; })
      .finally(function () { els.mealSplitSave.disabled = false; });
  });
  els.dayWindowChips.addEventListener("click", function (e) {
    var chip = e.target.closest("button.chip");
    if (!chip) return;
    dayWindow = chip.dataset.window || "";
    Array.prototype.forEach.call(els.dayWindowChips.querySelectorAll(".chip"), function (c) {
      c.classList.toggle("active", c === chip);
    });
    loadDay();
  });
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
    loadMealSplit();
    loadToday();
    loadDaily();
    loadQuant();
    loadDay();
  });
})();

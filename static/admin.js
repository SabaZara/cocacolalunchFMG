/* Admin: card management. Works with card_id only.
 *
 * Name/department are intentionally hidden. To re-enable later, flip
 * SHOW_NAMES to true — the table head, rows, and edit form all key off it,
 * so no rewrite is needed. */
(function () {
  "use strict";

  // ---- single flag to re-enable name/department columns later ------------ //
  var SHOW_NAMES = false;

  var els = {
    userLabel: document.getElementById("userLabel"),
    verBadge: document.getElementById("verBadge"),
    logoutBtn: document.getElementById("logoutBtn"),
    globalMsg: document.getElementById("globalMsg"),
    newCard: document.getElementById("newCard"),
    addBtn: document.getElementById("addBtn"),
    captureBtn: document.getElementById("captureBtn"),
    captureHint: document.getElementById("captureHint"),
    addMsg: document.getElementById("addMsg"),
    importFile: document.getElementById("importFile"),
    importBtn: document.getElementById("importBtn"),
    importMsg: document.getElementById("importMsg"),
    search: document.getElementById("search"),
    searchBtn: document.getElementById("searchBtn"),
    clearSearchBtn: document.getElementById("clearSearchBtn"),
    exportCsvBtn: document.getElementById("exportCsvBtn"),
    countLabel: document.getElementById("countLabel"),
    tableHead: document.getElementById("tableHead"),
    tableBody: document.getElementById("tableBody"),
    filterChips: document.getElementById("filterChips"),
    bulkBar: document.getElementById("bulkBar"),
    bulkCount: document.getElementById("bulkCount"),
    deleteAllBtn: document.getElementById("deleteAllBtn"),
    updateBtn: document.getElementById("updateBtn"),
    updateMsg: document.getElementById("updateMsg"),
    updateVer: document.getElementById("updateVer"),
    backupMsg: document.getElementById("backupMsg"),
    ghRepo: document.getElementById("ghRepo"),
    ghToken: document.getElementById("ghToken"),
    ghSaveBtn: document.getElementById("ghSaveBtn"),
    ghState: document.getElementById("ghState"),
    statTotal: document.getElementById("statTotal"),
    statAte: document.getElementById("statAte"),
    statActive: document.getElementById("statActive"),
    statRemaining: document.getElementById("statRemaining"),
  };

  // current filter + the people currently shown (after search+filter)
  var filter = "all";
  var shown = [];        // full list from the server
  var selected = {};     // id -> true
  var searchText = "";   // live client-side filter text

  function notice(container, text, kind) {
    container.innerHTML = text ? '<div class="notice ' + kind + '">' + text + "</div>" : "";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function api(method, url, body) {
    var opts = { method: method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { window.location.href = "/login"; throw new Error("auth"); }
      if (r.status === 204) return { ok: true, status: 204, j: null };
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, j: j }; });
    });
  }

  // ----------------------------- stats ------------------------------------ //
  function updateStats(people) {
    var active = 0, ate = 0;
    people.forEach(function (p) { if (p.active) active++; if (p.ate_today) ate++; });
    els.statTotal.textContent = people.length;
    els.statAte.textContent = ate;
    els.statActive.textContent = active;
    els.statRemaining.textContent = Math.max(active - ate, 0);
  }

  // ----------------------------- filtering -------------------------------- //
  function matchesFilter(p) {
    // text search (by card id, live)
    if (searchText && p.card_id.toLowerCase().indexOf(searchText) === -1) return false;
    switch (filter) {
      case "active": return p.active;
      case "inactive": return !p.active;
      case "ate": return p.ate_count > 0;
      case "notate": return p.ate_count === 0;
      default: return true;
    }
  }

  // ----------------------------- table ----------------------------------- //
  function renderHead() {
    var cols = ['<th class="sel"><input type="checkbox" class="allcheck" id="allCheck" /></th>',
                '<th class="ltr">ბარათის ID</th>'];
    if (SHOW_NAMES) { cols.push("<th>სახელი</th>"); cols.push("<th>დეპარტამენტი</th>"); }
    cols.push("<th>სტატუსი</th>", "<th>დღეს ნაჭამი</th>", "<th>დღიური ლიმიტი</th>",
              "<th>მოქმედებები</th>");
    els.tableHead.innerHTML = "<tr>" + cols.join("") + "</tr>";
    var all = document.getElementById("allCheck");
    if (all) all.addEventListener("change", function () { toggleAll(all.checked); });
  }

  function colspan() { return (SHOW_NAMES ? 6 : 4) + 2; }

  function rowHtml(p) {
    var isSel = !!selected[p.id];
    var full = p.ate_count >= p.daily_limit && p.daily_limit > 0;
    var cells = [
      '<td class="sel"><input type="checkbox" class="rowcheck" data-id="' + p.id + '"' + (isSel ? " checked" : "") + " /></td>",
      '<td class="ltr mono">' + esc(p.card_id) + "</td>",
    ];
    if (SHOW_NAMES) {
      cells.push("<td>" + esc(p.full_name) + "</td>");
      cells.push("<td>" + esc(p.department || "") + "</td>");
    }
    cells.push(
      "<td>" + (p.active
        ? '<span class="badge ok">აქტიური</span>'
        : '<span class="badge off">გათიშული</span>') + "</td>"
    );
    // today's meals as a count badge N / limit + a quick mark/clear toggle
    cells.push(
      '<td>' +
        '<span class="badge ' + (full ? "ok" : (p.ate_count > 0 ? "warn-badge" : "off")) + '">' +
          p.ate_count + " / " + p.daily_limit + "</span> " +
        '<label class="switch" title="ჭამა: სრულად მონიშვნა / მოხსნა" style="margin-inline-start:8px">' +
          '<input type="checkbox" data-act="ate" data-id="' + p.id + '"' + (full ? " checked" : "") + " />" +
          '<span class="track"></span></label>' +
      "</td>"
    );
    // editable per-person daily limit (data-orig used to revert on cancel)
    cells.push(
      '<td><input type="number" min="0" max="99" class="limit-input" data-act="limit" ' +
        'data-id="' + p.id + '" data-orig="' + p.daily_limit + '" value="' + p.daily_limit + '" /></td>'
    );
    cells.push(
      '<td class="actions">' +
        '<button class="small ghost" data-act="toggle" data-id="' + p.id + '" data-active="' + (p.active ? "1" : "0") + '">' +
          (p.active ? "გათიშვა" : "ჩართვა") + "</button> " +
        '<button class="small ghost" data-act="edit" data-id="' + p.id + '" data-card="' + esc(p.card_id) + '">რედაქტ.</button> ' +
        '<button class="small danger" data-act="delete" data-id="' + p.id + '" data-card="' + esc(p.card_id) + '">წაშლა</button>' +
      "</td>"
    );
    return '<tr data-id="' + p.id + '"' + (isSel ? ' class="selected"' : "") + ">" + cells.join("") + "</tr>";
  }

  function renderRows() {
    var list = shown.filter(matchesFilter);
    els.countLabel.textContent = "ნაჩვენებია: " + list.length;
    els.tableBody.innerHTML = list.map(rowHtml).join("") ||
      '<tr><td colspan="' + colspan() + '" style="text-align:center;color:var(--muted);padding:22px">ბარათები ვერ მოიძებნა</td></tr>';
    refreshBulkBar();
    syncAllCheck(list);
  }

  function syncAllCheck(list) {
    var all = document.getElementById("allCheck");
    if (!all) return;
    var visIds = list.map(function (p) { return p.id; });
    all.checked = visIds.length > 0 && visIds.every(function (id) { return selected[id]; });
  }

  function load() {
    // Always fetch the FULL list; search + filter are applied client-side
    // (instant, and stats always reflect the whole list).
    api("GET", "/api/people").then(function (res) {
      shown = res.j || [];
      var present = {};
      shown.forEach(function (p) { present[p.id] = true; });
      Object.keys(selected).forEach(function (id) { if (!present[id]) delete selected[id]; });
      renderRows();
      updateStats(shown);
    });
  }

  // ----------------------------- selection -------------------------------- //
  function selectedIds() { return Object.keys(selected).map(Number); }

  function refreshBulkBar() {
    var n = selectedIds().length;
    els.bulkCount.textContent = n + " მონიშნული";
    els.bulkBar.classList.toggle("hidden", n === 0);
  }

  function toggleAll(checked) {
    shown.filter(matchesFilter).forEach(function (p) {
      if (checked) selected[p.id] = true; else delete selected[p.id];
    });
    renderRows();
  }

  els.tableBody.addEventListener("change", function (e) {
    var rc = e.target.closest("input.rowcheck");
    if (rc) {
      var id = +rc.dataset.id;
      if (rc.checked) selected[id] = true; else delete selected[id];
      var tr = rc.closest("tr"); if (tr) tr.classList.toggle("selected", rc.checked);
      refreshBulkBar();
      syncAllCheck(shown.filter(matchesFilter));
      return;
    }
    var cb = e.target.closest('input[data-act="ate"]');
    if (cb) {
      var pid = cb.dataset.id, ate = cb.checked;
      var q = ate
        ? "დარწმუნებული ხართ, რომ გსურთ დღევანდელი ჭამის მონიშვნა?"
        : "დარწმუნებული ხართ, რომ გსურთ დღევანდელი ჭამის მოხსნა?";
      if (!confirm(q)) { cb.checked = !ate; return; }
      cb.disabled = true;
      api("POST", "/api/people/" + pid + "/ate", { ate: ate }).then(function (res) {
        if (!res.ok) { notice(els.globalMsg, (res.j && res.j.detail) || "ვერ შეიცვალა.", "bad"); cb.checked = !ate; cb.disabled = false; }
        else { notice(els.globalMsg, ate ? "მონიშნულია: სრული ჭამა." : "მოხსნილია დღევანდელი ჭამა.", "ok"); load(); }
      }).catch(function () { cb.checked = !ate; cb.disabled = false; });
      return;
    }
    var li = e.target.closest('input[data-act="limit"]');
    if (li) {
      var lid = li.dataset.id, val = parseInt(li.value, 10);
      var orig = li.dataset.orig != null ? li.dataset.orig : li.defaultValue;
      if (isNaN(val) || val < 0) { li.value = 0; val = 0; }
      if (String(val) === String(orig)) return; // no change
      if (!confirm("დარწმუნებული ხართ, რომ გსურთ დღიური ლიმიტის შეცვლა: " + orig + " → " + val + "?")) {
        li.value = orig;
        return;
      }
      li.disabled = true;
      api("PUT", "/api/people/" + lid, { daily_limit: val }).then(function (res) {
        if (!res.ok) { notice(els.globalMsg, (res.j && res.j.detail) || "ლიმიტი ვერ შეიცვალა.", "bad"); li.value = orig; }
        else { notice(els.globalMsg, "ლიმიტი განახლდა: " + val, "ok"); load(); }
        li.disabled = false;
      }).catch(function () { li.value = orig; li.disabled = false; });
    }
  });

  // --------------------------- row actions -------------------------------- //
  els.tableBody.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-act]");
    if (!btn) return;
    var act = btn.dataset.act, id = btn.dataset.id, card = btn.dataset.card;

    if (act === "toggle") {
      var enabling = btn.dataset.active === "0";
      var tq = enabling
        ? "დარწმუნებული ხართ, რომ გსურთ ბარათის ჩართვა?"
        : "დარწმუნებული ხართ, რომ გსურთ ბარათის გათიშვა?";
      if (!confirm(tq)) return;
      api("PUT", "/api/people/" + id, { active: enabling }).then(function (res) {
        if (!res.ok) notice(els.globalMsg, (res.j && res.j.detail) || "შეცდომა", "bad");
        load();
      });
    } else if (act === "delete") {
      if (!confirm('დარწმუნებული ხართ, რომ გსურთ ბარათის წაშლა? "' + card + '" — ისტორიაც წაიშლება.')) return;
      api("DELETE", "/api/people/" + id).then(function () { load(); });
    } else if (act === "edit") {
      var nv = prompt("ბარათის ახალი ID:", card);
      if (nv === null) return;
      nv = nv.trim(); if (!nv) return;
      if (nv === card) return;
      if (!confirm('დარწმუნებული ხართ, რომ გსურთ ბარათის შეცვლა: "' + card + '" → "' + nv + '"?')) return;
      api("PUT", "/api/people/" + id, { card_id: nv }).then(function (res) {
        if (!res.ok) notice(els.globalMsg, (res.j && res.j.detail) || "შეცდომა", "bad");
        else notice(els.globalMsg, "ბარათი განახლდა.", "ok");
        load();
      });
    }
  });

  // ----------------------------- bulk actions ----------------------------- //
  var BULK_LABEL = {
    delete: "წაშლა", activate: "ჩართვა", deactivate: "გათიშვა",
    ate: "ჭამის მონიშვნა", unate: "ჭამის მოხსნა", setlimit: "ლიმიტის დაყენება",
  };

  function runBulk(action, ids, all, value) {
    var body = all ? { action: action, all: true } : { action: action, ids: ids };
    if (value !== undefined) body.value = value;
    notice(els.globalMsg, "მიმდინარეობს…", "warn");
    api("POST", "/api/people/bulk", body).then(function (res) {
      if (!res.ok) { notice(els.globalMsg, (res.j && res.j.detail) || "ვერ შესრულდა.", "bad"); return; }
      notice(els.globalMsg, (BULK_LABEL[action] || action) + ": " + res.j.affected + " ბარათი.", "ok");
      if (action === "delete") selected = {};
      load();
    }).catch(function () { notice(els.globalMsg, "ვერ შესრულდა.", "bad"); });
  }

  els.bulkBar.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-bulk]");
    if (!btn) return;
    var action = btn.dataset.bulk;
    var ids = selectedIds();
    if (!ids.length) return;
    if (action === "setlimit") {
      var v = prompt("ახალი დღიური ლიმიტი მონიშნული " + ids.length + " ბარათისთვის:", "2");
      if (v === null) return;
      v = parseInt(v, 10);
      if (isNaN(v) || v < 0) { notice(els.globalMsg, "არასწორი რიცხვი.", "bad"); return; }
      if (!confirm("დარწმუნებული ხართ? ლიმიტი " + v + " დაუყენდება " + ids.length + " ბარათს.")) return;
      runBulk("setlimit", ids, false, v);
      return;
    }
    if (action === "delete") {
      if (!confirm("დარწმუნებული ხართ, რომ გსურთ მონიშნული " + ids.length + " ბარათის წაშლა? ისტორიაც წაიშლება.")) return;
    } else {
      if (!confirm("დარწმუნებული ხართ? (" + (BULK_LABEL[action] || action) + ": " + ids.length + " ბარათი)")) return;
    }
    runBulk(action, ids, false);
  });

  // delete ALL (double confirm)
  els.deleteAllBtn.addEventListener("click", function () {
    if (!confirm("ყველა ბარათის წაშლა? ეს ქმედება შეუქცევადია.")) return;
    if (!confirm("ნამდვილად ყველა? ბაზა დაცარიელდება.")) return;
    runBulk("delete", null, true);
  });

  // ------------------------------ add ------------------------------------- //
  function addCard() {
    var card = els.newCard.value.trim();
    if (!card) return;
    api("POST", "/api/people", { card_id: card }).then(function (res) {
      if (!res.ok) notice(els.addMsg, (res.j && res.j.detail) || "დამატება ვერ მოხერხდა.", "bad");
      else { notice(els.addMsg, "ბარათი დაემატა: " + esc(card), "ok"); els.newCard.value = ""; load(); }
    });
  }
  els.addBtn.addEventListener("click", addCard);
  els.newCard.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addCard(); }
  });

  els.captureBtn.addEventListener("click", function () {
    els.newCard.focus();
    els.captureHint.classList.remove("hidden");
    setTimeout(function () { els.captureHint.classList.add("hidden"); }, 4000);
  });

  // ----------------------------- import ----------------------------------- //
  els.importBtn.addEventListener("click", function () {
    var f = els.importFile.files[0];
    if (!f) { notice(els.importMsg, "აირჩიეთ ფაილი.", "warn"); return; }
    var fd = new FormData();
    fd.append("file", f);
    els.importBtn.disabled = true;
    notice(els.importMsg, "მიმდინარეობს იმპორტი…", "warn");
    fetch("/api/people/import", { method: "POST", body: fd })
      .then(function (r) { if (r.status === 401) { window.location.href = "/login"; throw new Error("auth"); } return r.json(); })
      .then(function (rep) {
        var parts = ["დაემატა: " + rep.added, "დუბლიკატი: " + rep.duplicate_count,
                     "შეცდომა: " + rep.invalid_count, "სულ ხაზი: " + rep.total_rows];
        var kind = rep.invalid_count > 0 || rep.duplicate_count > 0 ? "warn" : "ok";
        var html = parts.join(" • ");
        if (rep.duplicates && rep.duplicates.length)
          html += "<br><small>დუბლიკატები (ხაზი): " + rep.duplicates.map(function (d) { return d.row + ":" + esc(d.card_id); }).join(", ") + "</small>";
        if (rep.invalid && rep.invalid.length)
          html += "<br><small>შეცდომები (ხაზი): " + rep.invalid.map(function (d) { return d.row + ":" + esc(d.reason); }).join(", ") + "</small>";
        notice(els.importMsg, html, kind);
        els.importFile.value = "";
        load();
      })
      .catch(function () { notice(els.importMsg, "იმპორტი ვერ მოხერხდა.", "bad"); })
      .finally(function () { els.importBtn.disabled = false; });
  });

  // ----------------------------- search / filter / export ------------------ //
  // Live, as-you-type search (client-side filter of the loaded list).
  function applySearch() { searchText = els.search.value.trim().toLowerCase(); renderRows(); }
  els.search.addEventListener("input", applySearch);
  els.searchBtn.addEventListener("click", applySearch);
  els.search.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); applySearch(); } });
  els.clearSearchBtn.addEventListener("click", function () { els.search.value = ""; applySearch(); });

  els.filterChips.addEventListener("click", function (e) {
    var chip = e.target.closest("button.chip");
    if (!chip) return;
    filter = chip.dataset.filter;
    Array.prototype.forEach.call(els.filterChips.querySelectorAll(".chip"), function (c) {
      c.classList.toggle("active", c === chip);
    });
    renderRows();
  });

  els.exportCsvBtn.addEventListener("click", function () {
    window.location.href = "/api/people/export.csv";
  });

  // --------------------- backups (automatic; setup only) ------------------ //
  // Backups run on their own (weekly local + weekly GitHub). The only UI is a
  // one-time setup to arm GitHub with a repo + token; status shows if it's on.
  function loadBackupStatus() {
    if (!els.ghSaveBtn) return;
    api("GET", "/api/backup/status").then(function (res) {
      if (!res.ok || !res.j) return;
      var gh = res.j.github || {};
      if (gh.repo) els.ghRepo.value = gh.repo;
      els.ghToken.placeholder = gh.token_set ? "ტოკენი შენახულია ✓" : "GitHub ტოკენი";
      var st = gh.configured ? "GitHub ✓ ჩართულია (ავტომატური)" : "GitHub არ არის დაყენებული — ლოკალური ბექაფი მაინც კეთდება";
      if (gh.last_upload) st += " • ბოლო: " + String(gh.last_upload).replace("T", " ").replace("+00:00", "");
      if (gh.last_result && gh.last_result !== "ok") st += " • " + gh.last_result;
      els.ghState.textContent = st;
    });
  }

  if (els.ghSaveBtn) {
    els.ghSaveBtn.addEventListener("click", function () {
      var repo = els.ghRepo.value.trim();
      if (!repo) { notice(els.backupMsg, "მიუთითეთ რეპო (owner/repo).", "warn"); return; }
      api("POST", "/api/backup/github-config",
          { repo: repo, token: els.ghToken.value.trim() || null }).then(function (res) {
        if (res.ok) {
          notice(els.backupMsg, "შენახულია. ბექაფი ავტომატურად აიტვირთება.", "ok");
          els.ghToken.value = "";
          loadBackupStatus();
        } else {
          notice(els.backupMsg, (res.j && res.j.detail) || "ვერ შეინახა.", "bad");
        }
      });
    });
  }

  // ----------------------------- remote update --------------------------- //
  if (els.updateBtn) {
    // show current version next to the button
    fetch("/api/update/status").then(function (r) { return r.json(); })
      .then(function (s) {
        if (s && s.version) els.updateVer.textContent = "ვერსია v" + s.version + " • " + (s.repo || "");
      }).catch(function () {});

    els.updateBtn.addEventListener("click", function () {
      if (!confirm("ჩამოიტვირთოს უახლესი კოდი GitHub-იდან და გადაიტვირთოს აპლიკაცია?\n(მონაცემები არ წაიშლება)")) return;
      els.updateBtn.disabled = true;
      notice(els.updateMsg, "მიმდინარეობს განახლება… (დაახლ. 10–20 წამი)", "warn");
      api("POST", "/api/update").then(function (res) {
        if (!res.ok || !(res.j && res.j.ok)) {
          var out = res.j && res.j.output ? "<br><small>" + esc(res.j.output) + "</small>" : "";
          notice(els.updateMsg, "განახლება ვერ მოხერხდა." + out, "bad");
          els.updateBtn.disabled = false;
          return;
        }
        var msg = "კოდი განახლდა";
        if (res.j.restarting) {
          msg += " — აპლიკაცია გადაიტვირთება. დაელოდეთ ~10 წამს, შემდეგ განაახლეთ გვერდი (Ctrl+F5).";
        }
        if (res.j.output) msg += "<br><small>" + esc(res.j.output) + "</small>";
        notice(els.updateMsg, msg, "ok");
        // the app is restarting; poll /api/version and reload when it changes/returns
        var oldVer = (els.verBadge && els.verBadge.textContent) || "";
        var tries = 0;
        var iv = setInterval(function () {
          tries++;
          fetch("/api/version").then(function (r) { return r.json(); })
            .then(function (v) {
              if (v && v.version) {
                clearInterval(iv);
                notice(els.updateMsg, "განახლდა v" + v.version + ". იტვირთება…", "ok");
                setTimeout(function () { location.reload(); }, 1200);
              }
            }).catch(function () { /* app still restarting */ });
          if (tries > 30) { clearInterval(iv); els.updateBtn.disabled = false; }
        }, 2000);
      }).catch(function () {
        notice(els.updateMsg, "განახლება ვერ მოხერხდა (კავშირი).", "bad");
        els.updateBtn.disabled = false;
      });
    });
  }

  // ----------------------------- chrome ----------------------------------- //
  els.logoutBtn.addEventListener("click", function () {
    api("POST", "/api/logout").then(function () { window.location.href = "/login"; });
  });

  // show the running app version in the topbar (handy after an update)
  if (els.verBadge) {
    fetch("/api/version").then(function (r) { return r.json(); })
      .then(function (v) { if (v && v.version) els.verBadge.textContent = "v" + v.version; })
      .catch(function () {});
  }

  api("GET", "/api/me").then(function (res) {
    if (res.j && res.j.username) els.userLabel.textContent = res.j.username;
    renderHead();
    load();
    loadBackupStatus();
  });
})();

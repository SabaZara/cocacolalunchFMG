/* Admin: card management. Works with card_id only.
 *
 * Name/department are intentionally hidden. To re-enable later, flip
 * SHOW_NAMES to true — the table head, rows, and edit form all key off it,
 * so no rewrite is needed. */
(function () {
  "use strict";

  // Names are ON: cards register themselves as anonymous IDs, so the operator
  // needs a way to put a person to each one. The name cell is edited inline.
  // Department stays hidden (unused) — flip SHOW_DEPARTMENT to bring it back.
  var SHOW_NAMES = true;
  var SHOW_DEPARTMENT = false;

  // Placeholder the server stores when a card has no real name yet.
  var NAME_PLACEHOLDER = "----";

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
    globalLimit: document.getElementById("globalLimit"),
    saveLimitBtn: document.getElementById("saveLimitBtn"),
    limitMsg: document.getElementById("limitMsg"),
    countLabel: document.getElementById("countLabel"),
    tableHead: document.getElementById("tableHead"),
    tableBody: document.getElementById("tableBody"),
    filterChips: document.getElementById("filterChips"),
    bulkBar: document.getElementById("bulkBar"),
    bulkCount: document.getElementById("bulkCount"),
    deleteAllBtn: document.getElementById("deleteAllBtn"),
    updateBtn: document.getElementById("updateBtn"),
    updateSafeBtn: document.getElementById("updateSafeBtn"),
    updateMsg: document.getElementById("updateMsg"),
    updateVer: document.getElementById("updateVer"),
    backupMsg: document.getElementById("backupMsg"),
    ghRepo: document.getElementById("ghRepo"),
    ghToken: document.getElementById("ghToken"),
    ghSaveBtn: document.getElementById("ghSaveBtn"),
    ghTestBtn: document.getElementById("ghTestBtn"),
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
    // text search: card id OR name, live. Once cards carry names, searching
    // by name is the natural way to find somebody.
    if (searchText) {
      var hay = p.card_id.toLowerCase();
      if (p.full_name && p.full_name !== NAME_PLACEHOLDER) {
        hay += " " + p.full_name.toLowerCase();
      }
      if (hay.indexOf(searchText) === -1) return false;
    }
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
    if (SHOW_NAMES) cols.push("<th>სახელი</th>");
    if (SHOW_DEPARTMENT) cols.push("<th>დეპარტამენტი</th>");
    cols.push("<th>სტატუსი</th>", "<th>დღეს ნაჭამი</th>", "<th>დღიური ლიმიტი</th>",
              "<th>მოქმედებები</th>");
    els.tableHead.innerHTML = "<tr>" + cols.join("") + "</tr>";
    var all = document.getElementById("allCheck");
    if (all) all.addEventListener("change", function () { toggleAll(all.checked); });
  }

  function colspan() {
    return 6 + (SHOW_NAMES ? 1 : 0) + (SHOW_DEPARTMENT ? 1 : 0);
  }

  function rowHtml(p) {
    var isSel = !!selected[p.id];
    var full = p.ate_count >= p.daily_limit && p.daily_limit > 0;
    var cells = [
      '<td class="sel"><input type="checkbox" class="rowcheck" data-id="' + p.id + '"' + (isSel ? " checked" : "") + " /></td>",
      '<td class="ltr mono">' + esc(p.card_id) + "</td>",
    ];
    if (SHOW_NAMES) {
      // Inline-editable: type a name and it saves on blur / Enter. Cards
      // arrive anonymous (placeholder "----"), so this is the main way a
      // human name ever gets attached to a card id.
      var named = p.full_name && p.full_name !== NAME_PLACEHOLDER;
      cells.push(
        '<td><input type="text" class="name-input" data-act="name" ' +
          'data-id="' + p.id + '" ' +
          'data-orig="' + esc(named ? p.full_name : "") + '" ' +
          'value="' + esc(named ? p.full_name : "") + '" ' +
          'placeholder="სახელი…" ' +
          'title="დააჭირეთ და ჩაწერეთ სახელი" /></td>'
      );
    }
    if (SHOW_DEPARTMENT) {
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
    // The limit is ONE global number, not per card — show it, don't edit it
    // here (it is changed once, in the toolbar, for everybody).
    cells.push('<td class="mono">' + p.daily_limit + "</td>");
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
    return api("GET", "/api/people").then(function (res) {
      shown = res.j || [];
      var present = {};
      shown.forEach(function (p) { present[p.id] = true; });
      Object.keys(selected).forEach(function (id) { if (!present[id]) delete selected[id]; });
      renderRows();
      updateStats(shown);
    });
  }

  // ------------------------- live auto-refresh ---------------------------- //
  // Cards register themselves when people tap at the kiosk, so a list loaded
  // once goes stale within seconds. Poll so the page reflects reality without
  // anyone pressing F5 — but never redraw while the operator is mid-action,
  // because re-rendering the table would fight what they are doing.
  var AUTO_REFRESH_MS = 5000;
  var autoRefreshTimer = null;

  function busyEditing() {
    // A checked row / open bulk bar means a multi-step action is in progress.
    if (selectedIds().length > 0) return true;
    var a = document.activeElement;
    if (!a) return false;
    // Typing in any field (search, limit, add-card, backup config...).
    var tag = (a.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select";
  }

  function autoRefresh() {
    if (document.hidden) return;      // tab not visible: don't poll
    if (busyEditing()) return;        // don't yank the table mid-edit
    load();
  }

  function startAutoRefresh() {
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(autoRefresh, AUTO_REFRESH_MS);
  }

  // Refresh straight away when the operator comes back to the tab.
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) autoRefresh();
  });

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

  // Save a name when the operator leaves the field (blur) or presses Enter.
  // No confirm dialog: typing a name is low-stakes and confirming every one
  // while labelling a stack of cards would be unbearable.
  function saveName(input) {
    var pid = input.dataset.id;
    var val = (input.value || "").trim();
    var orig = input.dataset.orig || "";
    if (val === orig) return;                 // nothing changed
    input.disabled = true;
    // Clearing the box restores the server's placeholder.
    api("PUT", "/api/people/" + pid, { full_name: val || NAME_PLACEHOLDER })
      .then(function (res) {
        if (!res.ok) {
          notice(els.globalMsg, (res.j && res.j.detail) || "სახელი ვერ შეინახა.", "bad");
          input.value = orig;
        } else {
          input.dataset.orig = val;
          // Keep the in-memory list in step so the next auto-refresh does not
          // flash the old value back into the box.
          for (var i = 0; i < shown.length; i++) {
            if (String(shown[i].id) === String(pid)) {
              shown[i].full_name = val || NAME_PLACEHOLDER;
              break;
            }
          }
          notice(els.globalMsg, val ? "სახელი შენახულია: " + val : "სახელი მოიხსნა.", "ok");
        }
        input.disabled = false;
      }).catch(function () {
        input.value = orig;
        input.disabled = false;
      });
  }

  els.tableBody.addEventListener("blur", function (e) {
    var ni = e.target.closest && e.target.closest('input[data-act="name"]');
    if (ni) saveName(ni);
  }, true);   // capture: blur does not bubble

  els.tableBody.addEventListener("keydown", function (e) {
    var ni = e.target.closest && e.target.closest('input[data-act="name"]');
    if (!ni) return;
    if (e.key === "Enter") { e.preventDefault(); ni.blur(); }
    else if (e.key === "Escape") { ni.value = ni.dataset.orig || ""; ni.blur(); }
  });

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
    ate: "ჭამის მონიშვნა", unate: "ჭამის მოხსნა",
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

  // ------------------- global daily limit (one for all cards) -------------- //
  // There are no per-card limits: this single number applies to every card and
  // takes effect on the very next tap.
  var limitOrig = null;

  function loadLimit() {
    if (!els.globalLimit) return;
    api("GET", "/api/settings").then(function (res) {
      if (!res.ok || !res.j) return;
      limitOrig = res.j.daily_limit;
      els.globalLimit.value = limitOrig;
      if (res.j.max_daily_limit != null) els.globalLimit.max = res.j.max_daily_limit;
    });
  }

  if (els.saveLimitBtn) {
    els.saveLimitBtn.addEventListener("click", function () {
      var val = parseInt(els.globalLimit.value, 10);
      if (isNaN(val) || val < 0) {
        notice(els.globalMsg, "არასწორი რიცხვი.", "bad");
        return;
      }
      if (limitOrig !== null && val === limitOrig) return;
      if (!confirm("დღიური ლიმიტი შეიცვლება ყველა ბარათისთვის: " +
                   limitOrig + " → " + val + ". გავაგრძელოთ?")) {
        els.globalLimit.value = limitOrig;
        return;
      }
      els.saveLimitBtn.disabled = true;
      api("POST", "/api/settings", { daily_limit: val }).then(function (res) {
        if (!res.ok) {
          notice(els.globalMsg, (res.j && res.j.detail) || "ლიმიტი ვერ შეიცვალა.", "bad");
          els.globalLimit.value = limitOrig;
        } else {
          limitOrig = res.j.daily_limit;
          els.globalLimit.value = limitOrig;
          notice(els.globalMsg, "დღიური ლიმიტი განახლდა: " + limitOrig, "ok");
          load();   // the N / limit badges show the new number
        }
        els.saveLimitBtn.disabled = false;
      }).catch(function () {
        els.globalLimit.value = limitOrig;
        els.saveLimitBtn.disabled = false;
      });
    });
  }

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

  // Upload to GitHub RIGHT NOW. Without this the only way to find out whether
  // the token actually works is to wait for the weekly job and check the repo,
  // and a failure there is silent. This reports GitHub's exact answer.
  if (els.ghTestBtn) {
    els.ghTestBtn.addEventListener("click", function () {
      els.ghTestBtn.disabled = true;
      notice(els.backupMsg, "მიმდინარეობს ატვირთვა GitHub-ზე…", "warn");
      api("POST", "/api/backup/github-upload").then(function (res) {
        var j = res.j || {};
        if (res.ok && j.ok) {
          var kb = j.size ? " (" + Math.round(j.size / 1024) + " KB)" : "";
          notice(els.backupMsg,
            "✓ ატვირთულია GitHub-ზე: <b>" + esc(j.name || "") + "</b>" + kb +
            "<br>ბექაფი მუშაობს — შეამოწმეთ რეპოში საქაღალდე <b>backups/</b>.", "ok");
        } else {
          var err = j.error || (j.detail || "უცნობი შეცდომა");
          var hint = "";
          if (/401/.test(err)) {
            hint = "ტოკენი არასწორია ან არასრულად ჩაისვა — შექმენით ახალი და ჩასვით მთლიანად.";
          } else if (/404/.test(err)) {
            hint = "ტოკენს არ აქვს ამ პრივატულ რეპოზე წვდომა (საჭიროა <b>repo</b> უფლება), ან რეპოს სახელი არასწორია.";
          } else if (/403/.test(err)) {
            hint = "ტოკენს არ აქვს ჩაწერის უფლება — საჭიროა <b>repo</b> (ან Contents: Read and write).";
          }
          notice(els.backupMsg,
            "✗ ატვირთვა ვერ მოხერხდა: <b>" + esc(err) + "</b>" +
            (hint ? "<br>" + hint : ""), "bad");
        }
        loadBackupStatus();
        els.ghTestBtn.disabled = false;
      }).catch(function () {
        notice(els.backupMsg, "ატვირთვა ვერ მოხერხდა (კავშირის შეცდომა).", "bad");
        els.ghTestBtn.disabled = false;
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

    // Safe update: download the new code but DON'T restart. Python keeps
    // running the old code until the process restarts, which happens by itself
    // at the next login — so scanning is never interrupted mid-day.
    if (els.updateSafeBtn) {
      els.updateSafeBtn.addEventListener("click", function () {
        if (!confirm("ჩამოიტვირთოს უახლესი კოდი GitHub-იდან?\n\n" +
                     "აპლიკაცია არ გადაიტვირთება — სკანირება გაგრძელდება.\n" +
                     "ახალი ვერსია ამოქმედდება ლეპტოპის შემდეგი ჩართვისას.")) return;
        els.updateSafeBtn.disabled = true;
        notice(els.updateMsg, "მიმდინარეობს ჩამოტვირთვა…", "warn");
        api("POST", "/api/update?restart=false").then(function (res) {
          if (!res.ok || !(res.j && res.j.ok)) {
            var out = res.j && res.j.output ? "<br><small>" + esc(res.j.output) + "</small>" : "";
            notice(els.updateMsg, "ჩამოტვირთვა ვერ მოხერხდა." + out, "bad");
          } else {
            notice(els.updateMsg,
              "კოდი ჩამოიტვირთა ✓ — აპი აგრძელებს მუშაობას (v" +
              esc(res.j.version_before_restart || "") + ").<br>" +
              "ახალი ვერსია ამოქმედდება ლეპტოპის შემდეგი ჩართვისას.", "ok");
          }
          els.updateSafeBtn.disabled = false;
        }).catch(function () {
          notice(els.updateMsg, "ჩამოტვირთვა ვერ მოხერხდა (კავშირი).", "bad");
          els.updateSafeBtn.disabled = false;
        });
      });
    }

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
    loadLimit();
    loadBackupStatus();
    startAutoRefresh();   // keep the list live as people tap at the kiosk
  });
})();

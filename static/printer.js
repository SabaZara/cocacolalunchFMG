(function () {
  "use strict";
  var ids = ["receiptPrinter", "receiptEnabled", "printerRefresh", "printerTest",
    "printerSave", "printerInstall", "printerState", "printerMsg"];
  var el = {};
  ids.forEach(function (id) { el[id] = document.getElementById(id); });
  function message(text) { el.printerMsg.textContent = text; }
  function request(path, body) {
    return fetch("/api/printer" + path, body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail :
          "პრინტერის პარამეტრები ვერ ჩაიტვირთა. განახლების შემდეგ საჭიროა აპის რესტარტი.");
        return data;
      });
    });
  }
  function load() {
    return request("").then(function (data) {
      el.receiptPrinter.textContent = "";
      [""].concat(data.printers || []).forEach(function (name) {
        var option = document.createElement("option");
        option.value = name; option.textContent = name || "აირჩიეთ პრინტერი";
        el.receiptPrinter.appendChild(option);
      });
      if (data.printer && (data.printers || []).indexOf(data.printer) < 0) {
        var missing = document.createElement("option");
        missing.value = data.printer; missing.textContent = data.printer + " (მიუწვდომელია)";
        el.receiptPrinter.appendChild(missing);
      }
      el.receiptPrinter.value = data.printer;
      el.receiptEnabled.checked = data.enabled;
      el.printerInstall.hidden = !data.error;
      var q = data.queue || {};
      el.printerState.textContent = (data.enabled ? "ბეჭდვა ჩართულია. " : "ბეჭდვა გამორთულია. ") +
        "მოლოდინში: " + (q.pending || 0) + " · გაგზავნისას: " + (q.sending || 0) +
        " · შეცდომა: " + (q.failed || 0) + " · Windows-ში გაგზავნილი: " + (q.submitted || 0) +
        (data.error ? " — " + data.error : "");
    });
  }
  function perform(action) {
    [el.printerRefresh, el.printerSave, el.printerTest, el.printerInstall].forEach(function (button) { button.disabled = true; });
    message("მიმდინარეობს…");
    return action().catch(function (error) { message(error.message || "კავშირის შეცდომა"); })
      .finally(function () {
        [el.printerRefresh, el.printerSave, el.printerTest, el.printerInstall].forEach(function (button) { button.disabled = false; });
      });
  }
  el.printerRefresh.addEventListener("click", function () { perform(function () {
    return load().then(function () { message(""); });
  }); });
  el.printerTest.addEventListener("click", function () { perform(function () {
    return request("/test", {printer: el.receiptPrinter.value}).then(function (result) { message(result.message); });
  }); });
  el.printerSave.addEventListener("click", function () { perform(function () {
    return request("", {printer: el.receiptPrinter.value, enabled: el.receiptEnabled.checked})
      .then(load).then(function () { message("შენახულია — ცვლილება უკვე მოქმედებს."); });
  }); });
  el.printerInstall.addEventListener("click", function () { perform(function () {
    return request("/install", {}).then(function (result) {
      if (!result.ok) throw new Error(result.error);
      if (result.restart_required) {
        message("კომპონენტი დაყენდა. დააჭირეთ „განახლება + გადატვირთვა“, შემდეგ განაახლეთ პრინტერების სია.");
        return;
      }
      return load().then(function () { message("ბეჭდვის კომპონენტი მზადაა."); });
    });
  }); });
  load().catch(function (error) { message(error.message); });
})();

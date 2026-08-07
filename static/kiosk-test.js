(function () {
  "use strict";

  var frame = document.getElementById("kioskFrame");
  var log = document.getElementById("log");
  var manual = document.getElementById("manualCard");
  var manualBtn = document.getElementById("manualBtn");
  var repeatBtn = document.getElementById("repeatBtn");
  var sequenceBtn = document.getElementById("sequenceBtn");
  var clearBtn = document.getElementById("clearBtn");

  function addLog(text) {
    var li = document.createElement("li");
    li.textContent = text;
    log.prepend(li);
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function buttons(disabled) {
    document.querySelectorAll("button").forEach(function (b) {
      b.disabled = disabled;
    });
  }

  function kioskDoc() {
    return frame.contentDocument || frame.contentWindow.document;
  }

  async function tap(cardId, note) {
    var doc = kioskDoc();
    var input = doc.getElementById("capture");
    var screen = doc.getElementById("screen");
    var big = doc.getElementById("bigText");
    var sub = doc.getElementById("subText");

    if (!input || !screen || !big || !sub) {
      addLog("კიოსკი ჯერ არ ჩაიტვირთა.");
      return;
    }

    input.focus();
    input.value = cardId;
    input.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Enter",
      code: "Enter",
      bubbles: true,
      cancelable: true,
    }));

    await sleep(550);
    addLog(
      cardId + " → " + big.textContent +
      (sub.textContent ? " — " + sub.textContent : "") +
      (note ? " (" + note + ")" : "")
    );
  }

  document.querySelectorAll("button[data-card]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      tap(btn.dataset.card, btn.textContent.trim());
    });
  });

  manualBtn.addEventListener("click", function () {
    var value = manual.value.trim();
    if (!value) return;
    tap(value, "ხელით");
    manual.value = "";
  });

  manual.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      manualBtn.click();
    }
  });

  repeatBtn.addEventListener("click", async function () {
    buttons(true);
    await tap("1002", "პირველი ცდა");
    await sleep(2900);
    await tap("1002", "მეორე ცდა");
    buttons(false);
  });

  sequenceBtn.addEventListener("click", async function () {
    buttons(true);
    var cards = [
      ["1001", "აქტიური"],
      ["1001", "განმეორება"],
      ["0573856032", "წამყვანი ნულები"],
      ["9999", "გათიშული"],
      ["UNKNOWN-CARD", "უცნობი"],
    ];
    for (var i = 0; i < cards.length; i++) {
      await tap(cards[i][0], cards[i][1]);
      await sleep(2900);
    }
    buttons(false);
  });

  clearBtn.addEventListener("click", function () {
    log.innerHTML = "";
  });

  frame.addEventListener("load", function () {
    addLog("კიოსკის გვერდი ჩაიტვირთა.");
  });
})();

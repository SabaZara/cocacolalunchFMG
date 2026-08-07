/* Make every fetch() on this page send the ngrok-skip-browser-warning header,
 * so the free-tier ngrok interstitial page never interrupts the app's own
 * requests. Harmless when NOT served through ngrok (it's just an extra header).
 * Loaded first, before the page's own scripts. */
(function () {
  "use strict";
  if (window.__ngrokSkipPatched) return;
  window.__ngrokSkipPatched = true;
  var orig = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    var h = new Headers(init.headers || (input && input.headers) || {});
    if (!h.has("ngrok-skip-browser-warning")) {
      h.set("ngrok-skip-browser-warning", "true");
    }
    init.headers = h;
    return orig.call(this, input, init);
  };
})();

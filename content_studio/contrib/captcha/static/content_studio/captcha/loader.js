// The captcha widget's solver, from this site rather than a CDN. Loaded
// before cap.min.js; the widget's media passes the solver's URL.
(function () {
  var script = document.currentScript;
  var url = script && script.getAttribute("data-solver-url");
  if (url && !window.CAP_CUSTOM_WASM_URL) {
    window.CAP_CUSTOM_WASM_URL = new URL(url, document.baseURI).href;
  }
})();

(function () {
  "use strict";

  function start() {
    var form = document.getElementById("sso-redirect-form");
    if (!form) {
      return;
    }

    function showError() {
      var error = document.getElementById("sso-redirect-error");
      if (error) {
        error.hidden = false;
      }
      var button = form.querySelector("button");
      if (button) {
        button.focus();
      }
    }

    // Einmaliger Versuch, kein automatischer zweiter.
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        if (data && typeof data.url === "string" && data.url) {
          window.location.assign(data.url);
        } else {
          showError();
        }
      })
      .catch(showError);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

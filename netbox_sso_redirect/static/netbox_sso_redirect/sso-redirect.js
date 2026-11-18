(function () {
  "use strict";

  function start() {
    var form = document.getElementById("sso-redirect-form");
    if (!form) {
      return;
    }

    var button = form.querySelector("button");
    var pending = false;

    function showError() {
      var error = document.getElementById("sso-redirect-error");
      if (error) {
        error.hidden = false;
      }
      if (button) {
        button.disabled = false;
        button.focus();
      }
    }

    function attempt() {
      if (pending) {
        return;
      }
      pending = true;
      if (button) {
        button.disabled = true;
      }
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
            // Knopf bleibt deaktiviert, die Seite wird verlassen.
            window.location.assign(data.url);
          } else {
            pending = false;
            showError();
          }
        })
        .catch(function () {
          pending = false;
          showError();
        });
    }

    // Auch der manuelle Versuch läuft per fetch (CSP form-action).
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      attempt();
    });

    // Automatischer Start einmalig; Wiederholung nur per Klick.
    attempt();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

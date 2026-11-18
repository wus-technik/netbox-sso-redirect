(function () {
  "use strict";

  function start() {
    var form = document.getElementById("sso-redirect-form");
    if (!form) {
      return;
    }

    // Ohne fetch/FormData bleibt das normale Formular mit nativem Submit.
    if (typeof window.fetch !== "function" || typeof window.FormData !== "function") {
      return;
    }

    var button = form.querySelector("button");
    var pending = false;

    function showError() {
      var status = document.getElementById("sso-redirect-status");
      if (status) {
        status.hidden = true;
      }
      var error = document.getElementById("sso-redirect-error");
      if (error) {
        error.hidden = false;
        error.focus();
      }
      if (button) {
        button.disabled = false;
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
      var request;
      try {
        request = fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
      } catch (err) {
        // Synchroner Fehler: gleicher Fehlerpfad wie bei asynchronen.
        pending = false;
        showError();
        return;
      }
      request
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

    // Automatischer Start einmalig; Wiederholung nur per Klick. Nach einem SSO-Fehler
    // (data-autostart="false") wartet die Seite auf den Klick.
    if (form.getAttribute("data-autostart") !== "false") {
      attempt();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

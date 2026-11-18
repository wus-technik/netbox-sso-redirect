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
    var status = document.getElementById("sso-redirect-status");
    var error = document.getElementById("sso-redirect-error");
    var pending = false;

    function reset() {
      pending = false;
      if (status) {
        status.hidden = true;
      }
      if (button) {
        button.disabled = false;
      }
    }

    function showError() {
      reset();
      if (error) {
        error.hidden = false;
        error.focus();
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
      // Spinner bis zum Seitenwechsel, auch beim manuellen Versuch.
      if (status) {
        status.hidden = false;
      }
      if (error) {
        error.hidden = true;
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

    // Zurück vom IdP aus dem Back-Forward-Cache (v. a. iOS Safari): Die Seite käme sonst mit
    // Spinner und gesperrtem Knopf zurück. Kein erneuter Autostart, der Nutzer wollte zurück.
    window.addEventListener("pageshow", function (event) {
      if (event.persisted) {
        reset();
      }
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

(function () {
  "use strict";

  function start() {
    var form = document.getElementById("sso-redirect-form");
    if (!form) {
      return;
    }

    // Without fetch/FormData, keep the normal form and native submission.
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
      // Keep the spinner visible until navigation, including manual retries.
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
        // Synchronous failures use the same error path as asynchronous failures.
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
            // Keep the button disabled while navigating away.
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

    // Manual retries also use fetch to work with CSP form-action.
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      attempt();
    });

    // Returning from the IdP through the back-forward cache (especially iOS Safari) would
    // otherwise restore the spinner and disabled button. Do not auto-start when the user goes back.
    window.addEventListener("pageshow", function (event) {
      if (event.persisted) {
        reset();
      }
    });

    // Auto-start once; retry only on click. After an SSO error,
    // data-autostart="false" makes the page wait for a click.
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

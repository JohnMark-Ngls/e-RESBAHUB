/* e-RESBAHUB small helpers (no libraries). */
document.addEventListener("DOMContentLoaded", function () {
  var clock = document.querySelector("[data-live-clock]");
  var date = document.querySelector("[data-live-date]");
  if (clock && date) {
    var timeFormatter = new Intl.DateTimeFormat("en-PH", {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      hour12: true
    });
    var dateFormatter = new Intl.DateTimeFormat("en-PH", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric"
    });

    function updateClock() {
      var now = new Date();
      var localDate = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, "0") + "-" +
        String(now.getDate()).padStart(2, "0");
      clock.textContent = timeFormatter.format(now);
      clock.dateTime = now.toISOString();
      date.textContent = dateFormatter.format(now);
      date.dateTime = localDate;
    }

    updateClock();
    window.setInterval(updateClock, 1000);
  }

  // Close buttons on flash messages
  document.querySelectorAll(".flash button").forEach(function (b) {
    b.addEventListener("click", function () { b.parentElement.remove(); });
  });

  // Ask before dangerous actions:  <form data-confirm="Are you sure?">
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) { e.preventDefault(); }
    });
  });

  // Check upload size/count in the browser before sending (server checks again)
  var files = document.getElementById("documents");
  if (files) {
    files.addEventListener("change", function () {
      var total = 0;
      for (var i = 0; i < files.files.length; i++) { total += files.files[i].size; }
      var max = parseInt(files.getAttribute("data-max-files") || "3", 10);
      if (files.files.length > max) {
        alert("Please choose at most " + max + " files."); files.value = "";
      } else if (total > 5 * 1024 * 1024) {
        alert("Total upload size must be 5 MB or less."); files.value = "";
      }
    });
  }

  // Show/hide password fields from an inline eye button or legacy checkbox.
  document.querySelectorAll("[data-toggle-password]").forEach(function (toggle) {
    if (toggle.tagName === "BUTTON") {
      toggle.addEventListener("click", function () {
        var input = document.getElementById(toggle.getAttribute("data-toggle-password"));
        if (!input) { return; }

        var visible = input.type === "password";
        input.type = visible ? "text" : "password";
        toggle.setAttribute("aria-pressed", visible ? "true" : "false");
        toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
        toggle.classList.toggle("is-visible", visible);
      });
      return;
    }

    toggle.addEventListener("change", function () {
      document.querySelectorAll("input[type=password], input[data-was-password]").forEach(function (input) {
        if (toggle.checked) { input.type = "text"; input.setAttribute("data-was-password", "1"); }
        else if (input.getAttribute("data-was-password")) { input.type = "password"; }
      });
    });
  });
});

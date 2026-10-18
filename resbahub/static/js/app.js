/* e-RESBAHUB small helpers (no libraries). */
document.addEventListener("DOMContentLoaded", function () {
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

  // Show/hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (cb) {
    cb.addEventListener("change", function () {
      document.querySelectorAll("input[type=password], input[data-was-password]").forEach(function (i) {
        if (cb.checked) { i.type = "text"; i.setAttribute("data-was-password", "1"); }
        else if (i.getAttribute("data-was-password")) { i.type = "password"; }
      });
    });
  });
});

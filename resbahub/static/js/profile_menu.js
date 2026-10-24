
document.addEventListener("DOMContentLoaded", function () {
  const trigger = document.getElementById("profile-trigger");
  const dropdown = document.getElementById("profile-dropdown");
  const menu = document.getElementById("profile-menu");

  // PROFILE DROPDOWN
  if (trigger && dropdown && menu) {
    function closeDropdown() {
      dropdown.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    }

    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();

      const isOpen = dropdown.classList.toggle("open");
      trigger.setAttribute("aria-expanded", String(isOpen));
    });

    dropdown.addEventListener("click", function (event) {
      event.stopPropagation();
    });

    document.addEventListener("click", function () {
      closeDropdown();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeDropdown();
        trigger.focus();
      }
    });
  }

  // DARK MODE
  const themeButton = document.getElementById("dark-mode-button");
  const themeDescription = document.getElementById("theme-description");
  const themeIcon = document.getElementById("theme-icon");

  function setTheme(isDark) {
    document.body.classList.toggle("dark-mode", isDark);

    if (themeButton) {
      themeButton.setAttribute("aria-pressed", String(isDark));
    }

    if (themeDescription) {
      themeDescription.textContent = isDark
        ? "Switch to light mode"
        : "Switch to dark mode";
    }

    if (themeIcon) {
      themeIcon.textContent = isDark ? "☀" : "☾";
    }
  }

  let savedTheme = false;

  try {
    savedTheme = localStorage.getItem("eresbahub-theme") === "dark";
  } catch (error) {
    savedTheme = false;
  }

  setTheme(savedTheme);

  if (themeButton) {
    themeButton.addEventListener("click", function () {
      const isDark = !document.body.classList.contains("dark-mode");
      setTheme(isDark);

      try {
        localStorage.setItem(
          "eresbahub-theme",
          isDark ? "dark" : "light"
        );
      } catch (error) {
        // Dark mode still works if browser storage is unavailable.
      }
    });
  }

  // HELP & SUPPORT
  const helpButton = document.getElementById("help-button");

  if (helpButton) {
    helpButton.addEventListener("click", function () {
      alert(
        "e-RESBAHUB Help & Support\n\n" +
        "Please contact your barangay system administrator for assistance."
      );
    });
  }

  // REPORT A PROBLEM
  const reportButton = document.getElementById("report-problem-button");

  if (reportButton) {
    reportButton.addEventListener("click", function () {
      alert(
        "Report a Problem\n\n" +
        "Please contact your barangay system administrator " +
        "and describe the problem you encountered."
      );
    });
  }
});

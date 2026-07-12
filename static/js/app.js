/**
 * app.js
 * Shared chrome behavior: dark-mode persistence and the mobile sidebar drawer.
 * Feature-specific logic lives in predict.js / customers.js / charts.js.
 */

(function () {
    const root = document.documentElement;
    const themeToggle = document.getElementById("themeToggle");
    const STORAGE_KEY = "earlyshield-theme";

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        if (themeToggle) {
            const icon = themeToggle.querySelector("i");
            const label = themeToggle.querySelector("span");
            if (theme === "dark") {
                icon.className = "bi bi-sun";
                label.textContent = "Light mode";
            } else {
                icon.className = "bi bi-moon-stars";
                label.textContent = "Dark mode";
            }
        }
    }

    const savedTheme = localStorage.getItem(STORAGE_KEY) || "light";
    applyTheme(savedTheme);

    if (themeToggle) {
        themeToggle.addEventListener("click", function () {
            const current = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
            localStorage.setItem(STORAGE_KEY, current);
            applyTheme(current);
        });
    }

    const burger = document.getElementById("sidebarBurger");
    const sidebar = document.getElementById("sidebar");
    if (burger && sidebar) {
        burger.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
        document.addEventListener("click", function (event) {
            if (!sidebar.contains(event.target) && !burger.contains(event.target)) {
                sidebar.classList.remove("open");
            }
        });
    }

    // Auto-dismiss flash messages after a few seconds.
    document.querySelectorAll(".flash-stack .alert").forEach(function (alertEl) {
        setTimeout(function () {
            const instance = bootstrap.Alert.getOrCreateInstance(alertEl);
            instance.close();
        }, 6000);
    });
})();

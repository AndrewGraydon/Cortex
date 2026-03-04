/* Cortex web UI — minimal JavaScript for HTMX integration */

/**
 * Update the status indicator dot based on /api/health response.
 * Called via hx-on::after-request on the status indicator.
 */
function updateStatusDot(event) {
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");
    if (!dot || !text) return;

    try {
        const data = JSON.parse(event.detail.xhr.responseText);
        const status = data.status || "unknown";

        // Remove old status classes
        dot.classList.remove("healthy", "degraded", "unhealthy");
        dot.classList.add(status);

        text.textContent = status;
    } catch {
        dot.classList.remove("healthy", "degraded", "unhealthy");
        text.textContent = "error";
    }
}

/**
 * Toggle between light and dark DaisyUI themes.
 */
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    localStorage.setItem("cortex-theme", next);
}

/* Restore saved theme on load */
(function () {
    const saved = localStorage.getItem("cortex-theme");
    if (saved) {
        document.documentElement.setAttribute("data-theme", saved);
    }
})();

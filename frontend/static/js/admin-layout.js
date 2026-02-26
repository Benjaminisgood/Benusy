(function () {
    const MOBILE_BREAKPOINT = 960;

    function isMobileViewport() {
        return window.innerWidth <= MOBILE_BREAKPOINT;
    }

    function setupMobileNav() {
        const shell = document.querySelector(".admin-shell");
        const sidebar = shell?.querySelector(".sidebar");
        if (!shell || !sidebar) return;
        if (shell.dataset.mobileNavReady === "true") return;

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "admin-mobile-toggle";
        toggle.setAttribute("aria-label", "打开导航菜单");
        toggle.setAttribute("aria-expanded", "false");
        toggle.innerHTML = '<i class="fas fa-bars" aria-hidden="true"></i>';

        const overlay = document.createElement("div");
        overlay.className = "admin-sidebar-overlay";

        shell.appendChild(toggle);
        shell.appendChild(overlay);

        function setNavOpen(value) {
            shell.classList.toggle("nav-open", value);
            document.body.classList.toggle("admin-nav-open", value);
            toggle.setAttribute("aria-expanded", value ? "true" : "false");
        }

        toggle.addEventListener("click", () => {
            setNavOpen(!shell.classList.contains("nav-open"));
        });

        overlay.addEventListener("click", () => {
            setNavOpen(false);
        });

        sidebar.addEventListener("click", (event) => {
            const link = event.target.closest("a");
            if (!link || !isMobileViewport()) return;
            setNavOpen(false);
        });

        window.addEventListener("resize", () => {
            if (!isMobileViewport()) {
                setNavOpen(false);
            }
        });

        window.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                setNavOpen(false);
            }
        });

        setNavOpen(false);
        shell.dataset.mobileNavReady = "true";
    }

    function setNavActive() {
        const page = document.body.dataset.adminPage;
        document.querySelectorAll(".sidebar-nav a[data-nav]").forEach((link) => {
            const isActive = link.dataset.nav === page;
            link.classList.toggle("active", isActive);
        });
    }

    function bindLogout() {
        const logoutLink = document.getElementById("logout-link");
        if (!logoutLink) return;
        logoutLink.addEventListener("click", () => {
            clearAuth();
        });
    }

    function showAlert(message, type = "error") {
        const el = document.getElementById("page-alert");
        if (!el) return;
        el.textContent = message;
        el.className = `alert ${type}`;
    }

    function clearAlert() {
        const el = document.getElementById("page-alert");
        if (!el) return;
        el.textContent = "";
        el.className = "alert";
    }

    function setLastUpdated(value) {
        const chip = document.getElementById("last-updated-chip");
        if (!chip) return;
        if (value) {
            chip.textContent = `最近更新: ${formatDateTime(value)}`;
            return;
        }
        chip.textContent = `最近更新: ${formatDateTime(new Date().toISOString())}`;
    }

    async function init(options = {}) {
        const user = await requireUserWithRoles(["admin"]);
        const name = user.display_name || user.username || `管理员${user.id}`;

        const chip = document.getElementById("admin-user-chip");
        if (chip) {
            chip.textContent = `当前管理员: ${name}`;
        }

        const moduleChip = document.getElementById("current-module-chip");
        if (moduleChip && options.moduleLabel) {
            moduleChip.textContent = `模块: ${options.moduleLabel}`;
        }

        setNavActive();
        bindLogout();
        setupMobileNav();
        setLastUpdated();
        return user;
    }

    window.adminLayout = {
        init,
        showAlert,
        clearAlert,
        setLastUpdated,
    };
})();

(function () {
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

(function initUserLayout() {
    const shell = document.querySelector('.app-shell');
    const toggle = document.querySelector('[data-nav-toggle]');
    const overlay = document.querySelector('[data-nav-overlay]');
    const sidebar = document.querySelector('.sidebar');

    if (!shell || !toggle || !overlay || !sidebar) {
        return;
    }

    const MOBILE_BREAKPOINT = 960;

    function isMobileViewport() {
        return window.innerWidth <= MOBILE_BREAKPOINT;
    }

    function setOpenState(isOpen) {
        shell.classList.toggle('nav-open', isOpen);
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }

    toggle.addEventListener('click', () => {
        setOpenState(!shell.classList.contains('nav-open'));
    });

    overlay.addEventListener('click', () => {
        setOpenState(false);
    });

    sidebar.addEventListener('click', (event) => {
        const target = event.target.closest('a');
        if (!target || !isMobileViewport()) {
            return;
        }
        setOpenState(false);
    });

    window.addEventListener('resize', () => {
        if (!isMobileViewport()) {
            setOpenState(false);
        }
    });

    setOpenState(false);
})();

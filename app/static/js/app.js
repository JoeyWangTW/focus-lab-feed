/**
 * Focus Lab Feed Collector — SPA Router & State
 * Page modules are loaded from separate files.
 */

const App = {
    currentPage: null,
    pages: {},

    async init() {
        // Check setup status first
        const setupOk = await this.checkSetup();
        if (!setupOk) return; // Onboarding will call init() again when done

        // Register page modules (loaded from separate script files)
        this.pages = {
            platforms: window.PlatformsPage || { render: () => '<div class="empty-state"><div class="icon">&#9783;</div><p>Loading platforms...</p></div>' },
            collect: window.CollectPage || { render: () => '<div class="empty-state"><div class="icon">&#9655;</div><p>Loading collection...</p></div>' },
            viewer: window.ViewerPage || { render: () => '<div class="empty-state"><div class="icon">&#9776;</div><p>Loading viewer...</p></div>' },
            curated: window.CuratedPage || { render: () => '<div class="empty-state"><div class="icon">&#9734;</div><p>Loading curated feed...</p></div>' },
            export: window.ExportPage || { render: () => '<div class="empty-state"><div class="icon">&#8681;</div><p>Loading export...</p></div>' },
            curate: window.CuratePage || { render: () => '<div class="empty-state"><div class="icon">&#9883;</div><p>Loading curation...</p></div>' },
        };

        // Show main app
        document.getElementById('app').style.display = 'flex';

        // Populate workspace chip (runs once; refreshWorkspaceChip binds button handler)
        this.refreshWorkspaceChip();

        // Any page can fire `workspace:updated` after a setup/change to force
        // the sidebar chip to re-read /api/workspace. Cleaner than every call
        // site remembering to poke App.refreshWorkspaceChip directly.
        window.addEventListener('workspace:updated', () => this.refreshWorkspaceChip());

        // Cmd/Ctrl+R inside pywebview doesn't reload by default — wire it up.
        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && (e.key === 'r' || e.key === 'R')) {
                e.preventDefault();
                location.reload();
            }
        });

        // Theme toggle — light ⇄ dark, persisted in localStorage.
        const themeBtn = document.getElementById('theme-toggle');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                const isDark = document.documentElement.classList.toggle('dark');
                try { localStorage.setItem('focuslab:theme', isDark ? 'dark' : 'light'); } catch (e) {}
            });
        }

        // Nav click handlers
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const page = item.dataset.page;
                this.navigate(page);
            });
        });

        // Handle hash navigation
        window.addEventListener('hashchange', () => {
            const page = location.hash.slice(1) || 'platforms';
            this.navigate(page, false);
        });

        // Initial page
        const page = location.hash.slice(1) || 'platforms';
        this.navigate(page, false);
    },

    async checkSetup() {
        try {
            const status = await api('/setup/status');
            if (!status.setup_needed) return true;

            // Show onboarding
            this.showOnboarding();
            return false;
        } catch (e) {
            // If setup endpoint fails, continue anyway (dev mode without Playwright check)
            return true;
        }
    },

    showOnboarding() {
        document.getElementById('app').style.display = 'none';

        let overlay = document.getElementById('onboarding');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'onboarding';
            document.body.appendChild(overlay);
        }

        overlay.innerHTML = `
            <div class="onboarding-overlay">
                <div class="onboarding-content">
                    <div style="font-size:48px;margin-bottom:24px">🔬</div>
                    <h1>Focus Lab Feed</h1>
                    <p>First-time setup: we need to download a browser engine to collect social media feeds.</p>
                    <button class="btn btn-primary" id="setup-start-btn" onclick="App.startSetup()">
                        Set Up Now
                    </button>
                    <div id="setup-progress" class="onboarding-progress hidden">
                        <div class="progress-bar">
                            <div class="progress-fill" id="setup-bar" style="width:0%;animation:setup-pulse 2s infinite"></div>
                        </div>
                        <p id="setup-msg">Downloading Chromium browser...</p>
                    </div>
                </div>
            </div>
        `;
    },

    async startSetup() {
        const btn = document.getElementById('setup-start-btn');
        btn.classList.add('hidden');
        document.getElementById('setup-progress').classList.remove('hidden');

        try {
            await api('/setup/install', { method: 'POST' });

            // Poll until done
            let attempts = 0;
            while (attempts < 120) { // 5 minutes max (120 * 2.5s)
                await new Promise(r => setTimeout(r, 2500));
                const status = await api('/setup/status');

                if (!status.installing) {
                    if (status.install_result && !status.install_result.success) {
                        document.getElementById('setup-msg').textContent =
                            `Setup failed: ${status.install_result.message}`;
                        document.getElementById('setup-msg').classList.add('text-danger');
                        btn.classList.remove('hidden');
                        btn.textContent = 'Retry';
                        document.getElementById('setup-progress').classList.add('hidden');
                        return;
                    }

                    // Success!
                    document.getElementById('setup-bar').style.width = '100%';
                    document.getElementById('setup-bar').style.animation = 'none';
                    document.getElementById('setup-msg').textContent = 'Setup complete!';

                    await new Promise(r => setTimeout(r, 1000));

                    // Remove overlay and start app
                    const overlay = document.getElementById('onboarding');
                    if (overlay) overlay.remove();
                    App.init();
                    return;
                }
                attempts++;
            }

            document.getElementById('setup-msg').textContent = 'Setup timed out. Please try again.';
            document.getElementById('setup-msg').classList.add('text-danger');
        } catch (e) {
            document.getElementById('setup-msg').textContent = `Error: ${e.message}`;
            document.getElementById('setup-msg').classList.add('text-danger');
        }
    },

    async refreshWorkspaceChip() {
        try {
            const ws = await api('/workspace');
            const pathEl = document.getElementById('workspace-path');
            const openBtn = document.getElementById('workspace-open-btn');
            if (!pathEl || !openBtn) return;
            if (ws.is_setup) {
                const home = (ws.path || '').replace(/^\/Users\/[^/]+/, '~');
                pathEl.textContent = home;
                pathEl.title = ws.path || '';
                openBtn.textContent = 'Open folder';
                openBtn.disabled = false;
            } else {
                pathEl.textContent = 'Not set up';
                pathEl.title = '';
                openBtn.textContent = 'Go to Export to set up';
                openBtn.disabled = false;
                openBtn.onclick = () => { location.hash = 'export'; };
                return;
            }
            openBtn.onclick = async () => {
                try { await api('/workspace/reveal', { method: 'POST', body: JSON.stringify({}) }); }
                catch (e) { console.warn('Reveal failed:', e); }
            };
        } catch (e) {
            console.warn('Workspace info unavailable:', e);
        }
    },

    navigate(page, updateHash = true) {
        if (!this.pages[page]) page = 'platforms';

        // Update nav active state
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });

        if (updateHash) location.hash = page;

        // Render page
        const content = document.getElementById('content');
        const pageModule = this.pages[page];
        content.innerHTML = pageModule.render();

        // Add fade-in animation
        const wrapper = content.firstElementChild;
        if (wrapper) wrapper.classList.add('fade-in');

        if (pageModule.init) pageModule.init();
        this.currentPage = page;
    },
};

// Helper: fetch JSON from API
async function api(path, options = {}) {
    const res = await fetch(`/api${path}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

document.addEventListener('DOMContentLoaded', () => App.init());

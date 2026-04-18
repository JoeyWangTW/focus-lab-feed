/**
 * Export Page — two flows:
 *   1. Curated export → bootstrapped folder in user's workspace
 *      (Setup flow triggers if workspace not configured yet)
 *   2. Raw export → single JSON or CSV file in ~/Downloads/
 */
window.ExportPage = {
    runs: [],
    dates: [],
    workspace: null, // { is_setup, path, suggested_path, ... }

    render() {
        return `
            <div class="fade-in">
                <h1 class="page-title">Export</h1>

                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-3">Select runs</h3>
                    <div id="export-runs" class="mb-4">
                        <div class="text-secondary">Loading…</div>
                    </div>
                    <div class="flex items-center gap-2 mb-1">
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectAll()">Select all</button>
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectNone()">Select none</button>
                    </div>
                </div>

                <div class="card" id="curation-card">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-semibold text-subtitle">Curation export</h3>
                        <span class="text-secondary text-sm">Primary</span>
                    </div>
                    <p class="text-secondary text-sm mb-3">
                        Writes a ready-to-curate folder with <code>posts.json</code>, media, the mobile viewer,
                        and a copy of your <code>goals.md</code>. <code>cd</code> into it and your agent
                        (Claude Code / Cursor / Codex) will pick up the curator skill automatically.
                    </p>
                    <div id="curation-body"></div>
                </div>

                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-3">Raw export</h3>
                    <p class="text-secondary text-sm mb-3">
                        Single file in <code>~/Downloads/</code> — for analysis, backup, or piping elsewhere.
                        No media, no zip.
                    </p>
                    <div class="export-formats mb-3">
                        <label><input type="radio" name="raw-format" value="json" checked> JSON</label>
                        <label><input type="radio" name="raw-format" value="csv"> CSV</label>
                    </div>
                    <button class="btn btn-secondary" id="raw-export-btn" onclick="ExportPage.doRawExport()">
                        Export raw
                    </button>
                </div>
            </div>
        `;
    },

    async init() {
        // Runs
        try {
            const data = await api('/data/runs');
            this.dates = data.dates || [];
            this.runs = (data.runs || []).filter(r => r.has_posts);
            this.renderRuns();
        } catch (e) {
            document.getElementById('export-runs').innerHTML =
                `<div class="text-danger">Failed to load runs</div>`;
        }

        // Workspace — drives the curation card
        await this.refreshWorkspace();
    },

    async refreshWorkspace() {
        try {
            this.workspace = await api('/workspace');
        } catch (e) {
            this.workspace = { is_setup: false };
        }
        this.renderCurationBody();
    },

    renderCurationBody() {
        const body = document.getElementById('curation-body');
        if (!body) return;

        if (!this.workspace || !this.workspace.is_setup) {
            const suggested = (this.workspace && this.workspace.suggested_path) || '~/Focus Lab Feed';
            const hasPicker = !!(window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder);
            body.innerHTML = `
                <div class="setup-box">
                    <div class="setup-title">Set up a curation folder</div>
                    <p class="text-secondary text-sm mb-3">
                        Pick any folder (we'll create it if it doesn't exist) — packs will land inside an
                        <code>exports/</code> subfolder there, and we'll seed the curator skill, a blank
                        <code>goals.md</code>, and agent-discovery files so <code>claude</code> works out of the box.
                    </p>
                    <div class="setup-row">
                        <input type="text" id="setup-path" class="setup-input" value="${suggested.replace(/^\/Users\/[^/]+/, '~')}">
                        ${hasPicker ? '<button class="btn btn-secondary btn-sm" id="setup-pick-btn" onclick="ExportPage.pickFolder()">Choose…</button>' : ''}
                        <button class="btn btn-primary btn-sm" id="setup-btn" onclick="ExportPage.doSetup()">Create & set up</button>
                    </div>
                    <label class="setup-checkbox">
                        <input type="checkbox" id="setup-update-app-files" checked>
                        <span>If the folder already has a Focus Lab workspace, refresh the curator skill and agent instructions to this version. Your <code>goals.md</code> is never touched.</span>
                    </label>
                    <div class="text-secondary text-xs mt-2">
                        ${hasPicker
                            ? 'Tap <strong>Choose…</strong> for the native picker, or type a path. Pick something inside iCloud Drive for auto-sync.'
                            : 'Type a path. Pick something inside iCloud Drive if you want auto-sync across Macs.'}
                    </div>
                    <div id="setup-error" class="text-danger text-sm mt-2" hidden></div>
                </div>
            `;
            return;
        }

        const path = this.workspace.path || '';
        const pretty = path.replace(/^\/Users\/[^/]+/, '~');
        body.innerHTML = `
            <div class="curation-dir-row">
                <div class="curation-dir-label">Destination</div>
                <div class="curation-dir-path" title="${path}">${pretty}/exports/</div>
                <button class="btn btn-secondary btn-sm" onclick="ExportPage.changeWorkspace()">Change…</button>
            </div>
            <button class="btn btn-primary" id="curation-export-btn" onclick="ExportPage.doCurationExport()">
                Export for curation
            </button>
        `;
    },

    async pickFolder() {
        if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.pick_folder) return;
        const input = document.getElementById('setup-path');
        const initial = (input && input.value || '').replace(/^~/, '/Users/' + (navigator.userAgent.match(/Mac/) ? '' : ''));
        try {
            const picked = await window.pywebview.api.pick_folder('');
            if (picked && input) {
                input.value = picked.replace(/^\/Users\/[^/]+/, '~');
                input.dataset.absolute = picked;
            }
        } catch (e) {
            console.warn('Folder picker failed:', e);
        }
    },

    async doSetup() {
        const input = document.getElementById('setup-path');
        const errEl = document.getElementById('setup-error');
        const btn = document.getElementById('setup-btn');
        // Prefer the absolute path from the native picker if available (the input
        // shows a `~`-prettified version but the backend wants a real path).
        const absPath = (input && input.dataset && input.dataset.absolute) || '';
        const rawPath = (absPath || (input && input.value || '')).trim();
        if (!rawPath) { this._setupError('Please enter a folder path.'); return; }

        if (btn) { btn.disabled = true; btn.textContent = 'Setting up…'; }
        errEl.hidden = true;
        try {
            const updateCheckbox = document.getElementById('setup-update-app-files');
            const updateAppFiles = !!(updateCheckbox && updateCheckbox.checked);
            const r = await api('/workspace/setup', {
                method: 'POST',
                body: JSON.stringify({ path: rawPath, update_app_files: updateAppFiles }),
            });
            if (r.success) {
                await this.refreshWorkspace();
                window.dispatchEvent(new CustomEvent("workspace:updated"));
                const parts = [];
                if (r.created && r.created.length) parts.push(`${r.created.length} created`);
                if (r.updated && r.updated.length) parts.push(`${r.updated.length} updated`);
                const change = parts.length ? ` — ${parts.join(', ')}` : ' (nothing to change)';
                this._showToast(`Workspace ready at <strong>${r.workspace.replace(/^\/Users\/[^/]+/, '~')}</strong>${change}`);
            }
        } catch (e) {
            this._setupError(e.message || String(e));
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Create & set up'; }
        }
    },

    _setupError(msg) {
        const el = document.getElementById('setup-error');
        if (el) { el.textContent = msg; el.hidden = false; }
    },

    async changeWorkspace() {
        const current = this.workspace && this.workspace.path || '';
        let next = null;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
            try { next = await window.pywebview.api.pick_folder(current); }
            catch (e) { console.warn('Picker failed:', e); }
        }
        if (!next) {
            next = prompt('New workspace folder path:', current);
        }
        if (!next || next === current) return;
        try {
            await api('/workspace/setup', {
                method: 'POST',
                body: JSON.stringify({ path: next }),
            });
            await this.refreshWorkspace();
            window.dispatchEvent(new CustomEvent("workspace:updated"));
        } catch (e) {
            alert('Could not change workspace: ' + e.message);
        }
    },

    toggleTree(id) {
        const btn = document.querySelector(`[data-tree="${id}"]`);
        const children = document.getElementById(id);
        if (!btn || !children) return;
        btn.classList.toggle('open');
        children.classList.toggle('open');
    },

    toggleJobCheckboxes(jobId, checked) {
        document.querySelectorAll(`#${jobId} .export-run-chk`).forEach(c => c.checked = checked);
    },

    renderRuns() {
        const container = document.getElementById('export-runs');
        if (this.runs.length === 0) {
            container.innerHTML = '<div class="text-secondary">No runs available</div>';
            return;
        }

        let html = '';
        if (this.dates.length > 0) {
            for (let di = 0; di < this.dates.length; di++) {
                const dateGroup = this.dates[di];
                const dateId = `export-date-${di}`;
                const totalPosts = dateGroup.jobs.reduce((sum, j) =>
                    sum + j.platforms.filter(p => p.has_posts).reduce((s, p) => s + (p.post_count || 0), 0), 0);

                html += `<div class="tree-node">
                    <button class="tree-toggle" data-tree="${dateId}" onclick="ExportPage.toggleTree('${dateId}')">
                        <span class="chevron">&#9654;</span>
                        <span class="tree-label">${dateGroup.date}</span>
                        <span class="tree-meta">${totalPosts} posts</span>
                    </button>
                    <div class="tree-children" id="${dateId}">`;

                for (let ji = 0; ji < dateGroup.jobs.length; ji++) {
                    const job = dateGroup.jobs[ji];
                    const jobId = `${dateId}-job-${ji}`;
                    const jobPlatforms = job.platforms.filter(p => p.has_posts);
                    if (jobPlatforms.length === 0) continue;
                    const jobPosts = jobPlatforms.reduce((s, p) => s + (p.post_count || 0), 0);
                    const jobTime = job.started_at ? new Date(job.started_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '';

                    html += `<div class="tree-node">
                        <button class="tree-toggle" data-tree="${jobId}" onclick="ExportPage.toggleTree('${jobId}')">
                            <span class="chevron">&#9654;</span>
                            <input type="checkbox" onclick="event.stopPropagation(); ExportPage.toggleJobCheckboxes('${jobId}', this.checked)"
                                style="width:14px;height:14px;accent-color:var(--accent)">
                            <span class="tree-label">Job ${job.job_id}${jobTime ? ` — ${jobTime}` : ''}</span>
                            <span class="tree-meta">${jobPosts} posts</span>
                        </button>
                        <div class="tree-children" id="${jobId}">`;

                    for (const run of jobPlatforms) {
                        html += `<div class="tree-leaf">
                            <input type="checkbox" class="export-run-chk" value="${run.run_id}"
                                style="width:14px;height:14px;accent-color:var(--accent)">
                            <span class="badge badge-${run.platform}">${run.platform}</span>
                            <span class="flex-1">${run.post_count || '?'} posts</span>
                        </div>`;
                    }

                    html += `</div></div>`;
                }

                html += `</div></div>`;
            }
        } else {
            html = this.runs.map(run => `
                <div class="tree-leaf">
                    <input type="checkbox" class="export-run-chk" value="${run.run_id}">
                    <span class="font-semibold">${(run.platform || 'unknown').charAt(0).toUpperCase() + (run.platform || '').slice(1)}</span>
                    <span class="flex-1 text-secondary text-sm">${run.timestamp || run.run_id}</span>
                    <span class="text-secondary text-sm">${run.post_count || '?'} posts</span>
                </div>
            `).join('');
        }
        container.innerHTML = html;
    },

    selectAll() { document.querySelectorAll('.export-run-chk').forEach(c => c.checked = true); },
    selectNone() { document.querySelectorAll('.export-run-chk').forEach(c => c.checked = false); },

    _selectedRuns() {
        return [...document.querySelectorAll('.export-run-chk:checked')].map(c => c.value);
    },

    _showToast(html, timeoutMs = 8000) {
        let toast = document.getElementById('export-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'export-toast';
            document.getElementById('content').appendChild(toast);
        }
        toast.className = 'export-toast';
        toast.innerHTML = html;
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, timeoutMs);
    },

    async doCurationExport() {
        const runs = this._selectedRuns();
        if (runs.length === 0) { alert('Select at least one run'); return; }

        const btn = document.getElementById('curation-export-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }

        try {
            const r = await api('/export/curation', {
                method: 'POST',
                body: JSON.stringify({ run_ids: runs }),
            });
            if (r.success) {
                const pretty = r.path.replace(/^\/Users\/[^/]+/, '~');
                this._showToast(
                    `Pack ready at <strong>${pretty}</strong> — ${r.post_count} posts, ${r.media_count} media (${r.size}) ·
                     <a href="#" id="export-reveal" style="color:var(--accent);text-decoration:underline">Open folder</a>`
                );
                const reveal = document.getElementById('export-reveal');
                if (reveal) reveal.addEventListener('click', async (e) => {
                    e.preventDefault();
                    try { await api('/workspace/reveal', { method: 'POST', body: JSON.stringify({ path: r.path }) }); }
                    catch (err) { console.warn('Reveal failed:', err); }
                });
                window.dispatchEvent(new CustomEvent("workspace:updated"));
            }
        } catch (e) {
            alert('Curation export failed: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Export for curation'; }
        }
    },

    async doRawExport() {
        const runs = this._selectedRuns();
        if (runs.length === 0) { alert('Select at least one run'); return; }
        const format = document.querySelector('input[name="raw-format"]:checked').value;

        const btn = document.getElementById('raw-export-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }

        try {
            const r = await api('/export/raw', {
                method: 'POST',
                body: JSON.stringify({ run_ids: runs, format }),
            });
            if (r.success) {
                this._showToast(
                    `Saved <strong>${r.filename}</strong> to Downloads — ${r.post_count} posts (${r.size})`
                );
            }
        } catch (e) {
            alert('Raw export failed: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Export raw'; }
        }
    },
};

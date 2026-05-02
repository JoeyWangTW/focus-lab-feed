/**
 * Export page — one-time operation.
 *
 * Pick a day + platform tree, hit Export. Pack lands in the workspace folder
 * configured in Settings. There's no save-to-Downloads option here anymore
 * (raw export was rarely used and confused the flow); workspace setup and
 * the auto-export toggle have moved to the Settings page too — this page
 * stays focused on "select what, then export."
 */
window.ExportPage = {
    runs: [],
    dates: [],
    workspace: null,
    skillStatus: null,

    render() {
        return `
            <div class="fade-in">
                <h1 class="page-title">Export</h1>
                <p class="page-subtitle">
                    A one-time export. Pick the day and platforms you want, then export to the folder
                    you set up in <a href="#settings">Settings</a>.
                </p>

                <div class="card">
                    <div class="export-step-head">
                        <span class="export-step-num">1</span>
                        <div>
                            <h3 class="font-semibold text-subtitle">Choose day and platform</h3>
                            <p class="text-secondary text-sm mt-1">
                                Expand a date, then tick the platform rows you want. Selections across
                                multiple days are combined into one pack.
                            </p>
                        </div>
                    </div>
                    <div id="export-runs" class="mb-4">
                        <div class="text-secondary">Loading…</div>
                    </div>
                    <div class="flex items-center gap-2 mb-1">
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectAll()">Select all</button>
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectNone()">Select none</button>
                    </div>
                </div>

                <div class="card" id="export-action-card">
                    <div class="export-step-head">
                        <span class="export-step-num">2</span>
                        <div>
                            <h3 class="font-semibold text-subtitle">Export to your folder</h3>
                            <p class="text-secondary text-sm mt-1">
                                Writes a ready-to-curate pack — <code>posts.json</code>, media, mobile viewer,
                                and your <code>goals.md</code>.
                            </p>
                        </div>
                    </div>
                    <div id="export-action-body"></div>
                </div>
            </div>
        `;
    },

    async init() {
        try {
            const data = await api('/data/runs');
            this.dates = data.dates || [];
            this.runs = (data.runs || []).filter(r => r.has_posts);
            this.renderRuns();
        } catch (e) {
            const el = document.getElementById('export-runs');
            if (el) el.innerHTML = `<div class="text-danger">Failed to load runs</div>`;
        }
        await this.refreshWorkspace();
    },

    async refreshWorkspace() {
        try {
            this.workspace = await api('/workspace');
        } catch (e) {
            this.workspace = { is_setup: false };
        }
        try {
            this.skillStatus = await api('/workspace/skill-status');
        } catch (e) {
            this.skillStatus = null;
        }
        this.renderActionBody();
    },

    renderActionBody() {
        const body = document.getElementById('export-action-body');
        if (!body) return;
        if (!this.workspace || !this.workspace.is_setup) {
            body.innerHTML = `
                <div class="setup-box">
                    <div class="setup-title">No export folder set up yet</div>
                    <p class="text-secondary text-sm mb-3">
                        Pick a folder over in <a href="#settings">Settings</a> first — that's where packs land.
                    </p>
                    <a href="#settings" class="btn btn-primary btn-sm">Go to Settings</a>
                </div>
            `;
            return;
        }
        const path = this.workspace.path || '';
        const pretty = path.replace(/^\/Users\/[^/]+/, '~');
        const skillNotice = this._skillUpdateNotice();
        body.innerHTML = `
            <div class="curation-dir-row">
                <div class="curation-dir-label">Destination</div>
                <div class="curation-dir-path" title="${path}">${pretty}/exports/</div>
                <button class="btn btn-secondary btn-sm" onclick="ExportPage.openExportsFolder()">Open folder</button>
            </div>
            ${skillNotice}
            <button class="btn btn-primary btn-lg" id="curation-export-btn" onclick="ExportPage.doCurationExport()">
                Export selected runs
            </button>
        `;
    },

    _skillUpdateNotice() {
        const s = this.skillStatus;
        if (!s || !s.outdated) return '';
        return `
            <div class="skill-update-notice">
                <span class="skill-update-icon">✦</span>
                <div class="skill-update-text">
                    There's a new version of the curator skill
                    <span class="text-secondary">
                        (v${s.workspace_version} → v${s.shipped_version}).
                        Your <code>goals.md</code> is never touched.
                    </span>
                </div>
                <button class="btn btn-secondary btn-sm" id="skill-update-btn" onclick="ExportPage.updateSkill()">Update</button>
            </div>
        `;
    },

    async updateSkill() {
        const btn = document.getElementById('skill-update-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Updating…'; }
        try {
            const r = await api('/workspace/skill-update', { method: 'POST' });
            this.skillStatus = r.status;
            this.renderActionBody();
            this._showToast(`Curator skill updated to v${r.status.workspace_version}.`);
        } catch (e) {
            alert('Skill update failed: ' + e.message);
            if (btn) { btn.disabled = false; btn.textContent = 'Update'; }
        }
    },

    async openExportsFolder() {
        try {
            const ws = this.workspace || await api('/workspace');
            if (!ws || !ws.is_setup) return;
            await api('/workspace/reveal', {
                method: 'POST',
                body: JSON.stringify({ path: ws.exports_dir || ws.path }),
            });
        } catch (e) {
            console.warn('Reveal failed:', e);
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
        if (!container) return;
        if (this.runs.length === 0) {
            container.innerHTML = '<div class="text-secondary">No runs available — collect something first on the <a href="#collect">Collect</a> tab.</div>';
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
                window.dispatchEvent(new CustomEvent('workspace:updated'));
            }
        } catch (e) {
            alert('Export failed: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Export selected runs'; }
        }
    },
};

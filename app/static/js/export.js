/**
 * Export Page — export collected data in various formats
 */
window.ExportPage = {
    runs: [],

    render() {
        return `
            <div class="fade-in">
                <h1 class="page-title">Export</h1>
                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-3">Select Runs</h3>
                    <div id="export-runs" class="mb-4">
                        <div class="text-secondary">Loading...</div>
                    </div>
                    <div class="flex items-center gap-2 mb-1">
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectAll()">Select All</button>
                        <button class="btn btn-secondary btn-sm" onclick="ExportPage.selectNone()">Select None</button>
                    </div>
                </div>
                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-3">Export Format</h3>
                    <div class="export-formats">
                        <label>
                            <input type="radio" name="export-format" value="json" checked> JSON
                        </label>
                        <label>
                            <input type="radio" name="export-format" value="csv"> CSV
                        </label>
                        <label>
                            <input type="radio" name="export-format" value="focus_lab"> Focus Lab
                        </label>
                    </div>
                    <button class="btn btn-primary" id="export-btn" onclick="ExportPage.doExport()">Export</button>
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
            document.getElementById('export-runs').innerHTML =
                `<div class="text-danger">Failed to load runs</div>`;
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

    selectAll() {
        document.querySelectorAll('.export-run-chk').forEach(c => c.checked = true);
    },

    selectNone() {
        document.querySelectorAll('.export-run-chk').forEach(c => c.checked = false);
    },

    async doExport() {
        const selectedRuns = [...document.querySelectorAll('.export-run-chk:checked')].map(c => c.value);
        if (selectedRuns.length === 0) {
            alert('Select at least one run to export');
            return;
        }

        const format = document.querySelector('input[name="export-format"]:checked').value;
        const btn = document.querySelector('#export-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Exporting...'; }

        try {
            const result = await api('/export', {
                method: 'POST',
                body: JSON.stringify({ run_ids: selectedRuns, format }),
            });

            if (btn) { btn.disabled = false; btn.textContent = 'Export'; }

            if (result.success) {
                // Show success toast
                let toast = document.getElementById('export-toast');
                if (!toast) {
                    toast = document.createElement('div');
                    toast.id = 'export-toast';
                    document.getElementById('content').appendChild(toast);
                }
                toast.className = 'export-toast';
                toast.innerHTML = `Saved <strong>${result.filename}</strong> to Downloads — ${result.post_count} posts, ${result.media_count} media files (${result.size})`;
                toast.style.display = 'block';
                setTimeout(() => { toast.style.display = 'none'; }, 5000);
            }
        } catch (e) {
            if (btn) { btn.disabled = false; btn.textContent = 'Export'; }
            alert('Export failed: ' + e.message);
        }
    },
};

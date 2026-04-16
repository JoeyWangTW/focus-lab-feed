/**
 * AI Curation page — pick an agent, get a copy-paste launch + prompt, edit goals.md.
 */
window.CuratePage = {
    workspace: null,          // /api/workspace response
    goals: null,              // /api/workspace/goals response
    selectedAgent: 'claude-code',
    selectedPack: '',         // pack folder name (empty = workspace root)

    agents: [
        {
            id: 'claude-code',
            name: 'Claude Code',
            tagline: 'Anthropic\'s terminal agent',
            launchCmd: (path) => `cd ${quote(path)}\nclaude`,
            prompt: () => `curate this feed`,
            setup: 'Your workspace already has the skill installed at <code>.claude/skills/focus-lab-curator/</code>. Claude Code auto-discovers it.',
        },
        {
            id: 'cursor',
            name: 'Cursor',
            tagline: 'AI-first IDE',
            launchCmd: (path) => `cursor ${quote(path)}`,
            prompt: (path) => `Read \`skills/focus-lab-curator/SKILL.md\` and follow it to curate this feed — use my goals in \`goals.md\`, score posts from \`posts.json\`, and write \`posts.filtered.json\` in this folder.`,
            setup: 'Open the folder in Cursor; the skill is available at <code>skills/focus-lab-curator/SKILL.md</code>. For auto-invocation, copy it to <code>.cursor/rules/</code>.',
        },
        {
            id: 'codex',
            name: 'Codex CLI',
            tagline: 'OpenAI\'s terminal agent',
            launchCmd: (path) => `cd ${quote(path)}\ncodex --instructions skills/focus-lab-curator/SKILL.md`,
            prompt: () => `curate this feed`,
            setup: 'Point <code>--instructions</code> at the workspace skill file. Available via <code>npm i -g @openai/codex</code>.',
        },
        {
            id: 'any',
            name: 'Any other agent',
            tagline: 'Anything that reads a system prompt',
            launchCmd: (path) => `cd ${quote(path)}\n# then launch your agent here`,
            prompt: (path) => [
                `You are in a Focus Lab Feed workspace: ${path}`,
                ``,
                `Read \`skills/focus-lab-curator/SKILL.md\` in full and follow it exactly.`,
                `It will ask you to read my preferences in \`goals.md\`, score posts from`,
                `\`posts.json\`, and write \`posts.filtered.json\` in this folder.`,
                `Preserve every original post field. Never drop posts. Sort by score desc.`,
            ].join('\n'),
            setup: 'Paste the contents of <code>skills/focus-lab-curator/SKILL.md</code> into your agent\'s system prompt.',
        },
    ],

    render() {
        return `
            <div class="fade-in">
                <h1 class="page-title">AI Curation</h1>
                <p class="text-secondary mb-4">
                    Turn a collected pack into a goal-aligned feed. Edit your preferences, pick your agent,
                    and copy the launch command.
                </p>
                <div id="curate-body">
                    <div class="empty-state"><p class="text-secondary">Loading…</p></div>
                </div>
            </div>
        `;
    },

    async init() {
        // Load workspace + goals in parallel
        const [ws, goals] = await Promise.all([
            api('/workspace').catch(() => ({ is_setup: false })),
            api('/workspace/goals').catch(() => null),
        ]);
        this.workspace = ws;
        this.goals = goals;
        this.renderBody();
    },

    renderBody() {
        const body = document.getElementById('curate-body');
        if (!body) return;

        if (!this.workspace || !this.workspace.is_setup) {
            body.innerHTML = `
                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-2">Workspace not set up</h3>
                    <p class="text-secondary text-sm mb-3">
                        Head over to <strong>Export</strong> to pick a curation folder. Once set up, come
                        back here to wire up your agent.
                    </p>
                    <a href="#export" class="btn btn-primary">Go to Export</a>
                </div>
            `;
            return;
        }

        body.innerHTML = `
            ${this._renderPackPicker()}
            ${this._renderAgentPicker()}
            ${this._renderCommands()}
            ${this._renderGoalsEditor()}
        `;

        // Wire handlers
        document.querySelectorAll('[data-agent-id]').forEach(el => {
            el.addEventListener('click', () => {
                this.selectedAgent = el.dataset.agentId;
                this.renderBody();
            });
        });
        const packSel = document.getElementById('pack-select');
        if (packSel) {
            packSel.addEventListener('change', (e) => {
                this.selectedPack = e.target.value;
                this._refreshCommands();
            });
        }
        const saveBtn = document.getElementById('goals-save');
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveGoals());

        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', () => this._copyToClipboard(btn));
        });
    },

    _packFullPath() {
        const ws = this.workspace && this.workspace.path || '';
        if (!this.selectedPack) return ws;  // workspace root
        return `${ws}/exports/${this.selectedPack}`;
    },

    _renderPackPicker() {
        const packs = (this.workspace && this.workspace.recent_packs) || [];
        const options = ['<option value="">Workspace root</option>']
            .concat(packs.filter(p => p.is_dir).map(p =>
                `<option value="${escapeAttr(p.name)}">${escapeHTML(p.name)}</option>`
            ));
        return `
            <div class="card">
                <h3 class="font-semibold text-subtitle mb-3">Pack to curate</h3>
                <select id="pack-select" class="setup-input" style="width:100%">
                    ${options.join('')}
                </select>
                ${packs.filter(p => p.is_dir).length === 0
                    ? '<p class="text-secondary text-sm mt-2">No packs yet — go to <strong>Export</strong> and create one.</p>'
                    : '<p class="text-secondary text-sm mt-2">Pick a pack to curate — the commands below will cd into it.</p>'
                }
            </div>
        `;
    },

    _renderAgentPicker() {
        return `
            <div class="card">
                <h3 class="font-semibold text-subtitle mb-3">Your agent</h3>
                <div class="agent-grid">
                    ${this.agents.map(a => `
                        <button class="agent-card ${a.id === this.selectedAgent ? 'selected' : ''}"
                                data-agent-id="${a.id}">
                            <div class="agent-name">${a.name}</div>
                            <div class="agent-tagline">${a.tagline}</div>
                        </button>
                    `).join('')}
                </div>
                <div class="agent-setup text-secondary text-sm mt-3">
                    ${this.agents.find(a => a.id === this.selectedAgent).setup}
                </div>
            </div>
        `;
    },

    _renderCommands() {
        const agent = this.agents.find(a => a.id === this.selectedAgent);
        const path = this._packFullPath();
        const launch = agent.launchCmd(path);
        const prompt = agent.prompt(path);

        return `
            <div class="card" id="commands-card">
                <h3 class="font-semibold text-subtitle mb-3">Launch</h3>
                <p class="text-secondary text-sm mb-2">Run this in your terminal:</p>
                <div class="code-block-wrap">
                    <pre class="code-block" id="launch-code">${escapeHTML(launch)}</pre>
                    <button class="copy-btn" data-copy-target="launch-code">Copy</button>
                </div>

                <h3 class="font-semibold text-subtitle mb-3 mt-4">Prompt</h3>
                <p class="text-secondary text-sm mb-2">Then paste this to your agent:</p>
                <div class="code-block-wrap">
                    <pre class="code-block" id="prompt-code">${escapeHTML(prompt)}</pre>
                    <button class="copy-btn" data-copy-target="prompt-code">Copy</button>
                </div>
            </div>
        `;
    },

    _refreshCommands() {
        const card = document.getElementById('commands-card');
        if (!card) return;
        const agent = this.agents.find(a => a.id === this.selectedAgent);
        const path = this._packFullPath();
        document.getElementById('launch-code').textContent = agent.launchCmd(path);
        document.getElementById('prompt-code').textContent = agent.prompt(path);
    },

    _renderGoalsEditor() {
        const content = (this.goals && this.goals.content) || '';
        const exists = !!(this.goals && this.goals.exists);
        return `
            <div class="card">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold text-subtitle">Your goals</h3>
                    <span class="text-secondary text-xs">
                        ${exists ? 'Saved to <code>goals.md</code>' : 'Not yet saved'}
                    </span>
                </div>
                <p class="text-secondary text-sm mb-2">
                    These preferences drive how the curator scores your posts. The first time you run
                    an agent in a pack, it\'ll also offer to interview you and write this for you.
                </p>
                <textarea id="goals-textarea" class="goals-textarea" rows="16" spellcheck="false">${escapeHTML(content)}</textarea>
                <div class="flex items-center gap-2 mt-3">
                    <button class="btn btn-primary" id="goals-save">Save goals</button>
                    <span class="text-secondary text-sm" id="goals-status"></span>
                </div>
            </div>
        `;
    },

    async saveGoals() {
        const ta = document.getElementById('goals-textarea');
        if (!ta) return;
        const status = document.getElementById('goals-status');
        const btn = document.getElementById('goals-save');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
        try {
            const r = await api('/workspace/goals', {
                method: 'POST',
                body: JSON.stringify({ content: ta.value }),
            });
            if (r.success) {
                this.goals = { content: ta.value, path: r.path, exists: true };
                if (status) { status.textContent = 'Saved.'; setTimeout(() => { status.textContent = ''; }, 2500); }
            }
        } catch (e) {
            if (status) status.textContent = 'Save failed: ' + e.message;
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Save goals'; }
        }
    },

    async _copyToClipboard(btn) {
        const targetId = btn.dataset.copyTarget;
        const target = document.getElementById(targetId);
        if (!target) return;
        const text = target.textContent;
        try {
            await navigator.clipboard.writeText(text);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        } catch (e) {
            // Fallback
            const range = document.createRange();
            range.selectNode(target);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            document.execCommand('copy');
            window.getSelection().removeAllRanges();
        }
    },
};

// ----- helpers -----
function quote(path) {
    if (!path) return '.';
    return path.includes(' ') ? `"${path}"` : path;
}

function escapeHTML(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeAttr(s) {
    return escapeHTML(s);
}

/**
 * "How to" page — a walkthrough of the full flow:
 * Connect → Collect → View (raw) OR Curate (agent) → View (curated) → ship
 *
 * Step 3b ("Curate") embeds the live agent picker + copy-paste launch command
 * + goals editor so the instructions are actionable in place, not just prose.
 */
window.CuratePage = {
    workspace: null,          // /api/workspace
    goals: null,              // /api/workspace/goals
    packs: [],                // /api/curated/packs
    selectedAgent: 'claude-code',
    selectedPack: '',

    agents: [
        {
            id: 'claude-code',
            name: 'Claude Code',
            tagline: "Anthropic's terminal agent",
            launchCmd: (path) => `cd ${quote(path)}\nclaude`,
            prompt: () => `curate this feed`,
            setup: 'Your workspace has the skill installed at <code>.claude/skills/focus-lab-curator/</code> — Claude Code auto-discovers it.',
        },
        {
            id: 'cursor',
            name: 'Cursor',
            tagline: 'AI-first IDE',
            launchCmd: (path) => `cursor ${quote(path)}`,
            prompt: () => `Read \`skills/focus-lab-curator/SKILL.md\` and follow it to curate this feed — use my goals in \`goals.md\`, score posts from \`posts.json\`, and write \`posts.filtered.json\` in this folder.`,
            setup: 'Open the folder in Cursor; the skill is at <code>skills/focus-lab-curator/SKILL.md</code>. Copy into <code>.cursor/rules/</code> for auto-invocation.',
        },
        {
            id: 'codex',
            name: 'Codex CLI',
            tagline: "OpenAI's terminal agent",
            launchCmd: (path) => `cd ${quote(path)}\ncodex --instructions skills/focus-lab-curator/SKILL.md`,
            prompt: () => `curate this feed`,
            setup: 'Point <code>--instructions</code> at the workspace skill file.',
        },
        {
            id: 'any',
            name: 'Any other agent',
            tagline: 'Anything that reads a system prompt',
            launchCmd: (path) => `cd ${quote(path)}\n# launch your agent here`,
            prompt: (path) => [
                `You are in a Focus Lab Feed workspace: ${path}`,
                ``,
                `Read \`skills/focus-lab-curator/SKILL.md\` in full and follow it exactly.`,
                `Use my preferences in \`goals.md\`, score posts from \`posts.json\`,`,
                `and write \`posts.filtered.json\` in this folder. Preserve every`,
                `original field. Sort by score desc.`,
            ].join('\n'),
            setup: "Paste <code>skills/focus-lab-curator/SKILL.md</code> into your agent's system prompt.",
        },
    ],

    render() {
        return `
            <div class="fade-in">
                <h1 class="page-title">Instructions</h1>
                <p class="text-secondary mb-4">
                    Scroll your social feeds for you, let your own AI agent curate them, and get back a feed you actually want to open.
                </p>
                <div id="howto-body">
                    <div class="empty-state"><p class="text-secondary">Loading…</p></div>
                </div>
            </div>
        `;
    },

    async init() {
        const [ws, goals, curated] = await Promise.all([
            api('/workspace').catch(() => ({ is_setup: false })),
            api('/workspace/goals').catch(() => null),
            api('/curated/packs').catch(() => ({ packs: [] })),
        ]);
        this.workspace = ws;
        this.goals = goals;
        this.packs = (curated && curated.packs) || [];
        this.selectedPack = this.packs[0] ? this.packs[0].name : '';
        this.renderBody();
    },

    renderBody() {
        const body = document.getElementById('howto-body');
        if (!body) return;

        body.innerHTML = [
            this._stepConnect(),
            this._stepCollect(),
            this._stepView(),
            this._stepCurate(),
            this._stepShip(),
        ].join('');

        // Wire agent cards
        document.querySelectorAll('[data-agent-id]').forEach(el => {
            el.addEventListener('click', () => {
                this.selectedAgent = el.dataset.agentId;
                this.renderBody();
            });
        });

        // Pack selector (used in the launch command)
        const packSel = document.getElementById('howto-pack-select');
        if (packSel) {
            packSel.addEventListener('change', (e) => {
                this.selectedPack = e.target.value;
                this._refreshCommands();
            });
        }

        // Goals save
        const saveBtn = document.getElementById('goals-save');
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveGoals());

        // Copy buttons
        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', () => this._copyToClipboard(btn));
        });
    },

    // ---- Steps ----

    _stepConnect() {
        return `
            <div class="howto-step">
                <div class="howto-step-num">1</div>
                <div class="howto-step-body">
                    <h3 class="font-semibold text-subtitle mb-2">Connect a platform</h3>
                    <p class="text-secondary text-sm mb-2">
                        Go to <a href="#platforms">Platforms</a> and click the one you want to collect from — Twitter/X, Threads, Instagram, or YouTube.
                        A real browser window opens; log in like you normally would. The app stores the session locally so it can scroll on your behalf later.
                    </p>
                    <p class="text-secondary text-xs">
                        Nothing is sent to a server. No API tokens. Just automation of what you'd do yourself.
                    </p>
                </div>
            </div>
        `;
    },

    _stepCollect() {
        return `
            <div class="howto-step">
                <div class="howto-step-num">2</div>
                <div class="howto-step-body">
                    <h3 class="font-semibold text-subtitle mb-2">Collect a feed</h3>
                    <p class="text-secondary text-sm mb-2">
                        Go to <a href="#collect">Collect</a>. Pick which connected platforms to include and how long to scroll. Hit Start.
                        The app scrolls each platform in the background and captures posts + media into <code>feed_data/</code>.
                    </p>
                    <p class="text-secondary text-xs">
                        Each run is timestamped. You can run it as often as you like — data accumulates.
                    </p>
                </div>
            </div>
        `;
    },

    _stepView() {
        return `
            <div class="howto-step">
                <div class="howto-step-num">3a</div>
                <div class="howto-step-body">
                    <h3 class="font-semibold text-subtitle mb-2">View raw <span class="text-secondary text-sm">(quick)</span></h3>
                    <p class="text-secondary text-sm">
                        Head to <a href="#viewer">Feed</a> — every collected post, filterable by platform, sortable by time / likes / reposts / replies. Fast way to see what's there.
                    </p>
                </div>
            </div>
        `;
    },

    _stepCurate() {
        const isSetup = this.workspace && this.workspace.is_setup;
        const hasPack = this.packs.length > 0;
        const agent = this.agents.find(a => a.id === this.selectedAgent);
        const path = this._packFullPath();

        return `
            <div class="howto-step">
                <div class="howto-step-num">3b</div>
                <div class="howto-step-body">
                    <h3 class="font-semibold text-subtitle mb-2">Curate, then view <span class="text-secondary text-sm">(recommended for phone)</span></h3>
                    <p class="text-secondary text-sm mb-3">
                        Export the posts into a pack, run your AI agent against it, then open the filtered result in <strong>AI Curation</strong>.
                        On first run the agent will interview you and write <code>goals.md</code>; after that it scores every post (0–100) and drops the drain.
                    </p>

                    <div class="howto-substep">
                        <div class="howto-substep-label">i. Export a pack</div>
                        <p class="text-secondary text-sm">
                            Go to <a href="#export">Export</a> → <em>Export for curation</em>.
                            ${isSetup
                                ? 'A folder lands in <code>' + esc(this.workspace.path.replace(/^\/Users\/[^/]+/, '~')) + '/exports/</code>.'
                                : "First time you'll pick a workspace folder — that's where packs live."}
                        </p>
                    </div>

                    <div class="howto-substep">
                        <div class="howto-substep-label">ii. Run your agent</div>
                        ${!isSetup || !hasPack ? `
                            <p class="text-secondary text-sm">
                                ${!isSetup ? "Set up a workspace on the Export page first." : "No packs exported yet — come back here after you've run an Export."}
                            </p>
                        ` : `
                            <p class="text-secondary text-sm mb-2">Pick your agent and pack — we'll generate a ready-to-paste command.</p>

                            <div class="howto-row">
                                <label class="text-secondary text-xs">Pack</label>
                                <select id="howto-pack-select" class="setup-input">
                                    ${this.packs.filter(p => true).map(p =>
                                        `<option value="${escAttr(p.name)}"${p.name === this.selectedPack ? ' selected' : ''}>${esc(p.name)}</option>`
                                    ).join('')}
                                </select>
                            </div>

                            <div class="agent-grid">
                                ${this.agents.map(a => `
                                    <button class="agent-card ${a.id === this.selectedAgent ? 'selected' : ''}"
                                            data-agent-id="${a.id}">
                                        <div class="agent-name">${a.name}</div>
                                        <div class="agent-tagline">${a.tagline}</div>
                                    </button>
                                `).join('')}
                            </div>
                            <div class="agent-setup text-secondary text-sm mt-3 mb-3">${agent.setup}</div>

                            <div class="howto-sublabel">Run this in your terminal</div>
                            <div class="code-block-wrap">
                                <pre class="code-block" id="launch-code">${esc(agent.launchCmd(path))}</pre>
                                <button class="copy-btn" data-copy-target="launch-code">Copy</button>
                            </div>

                            <div class="howto-sublabel">Then paste this to the agent</div>
                            <div class="code-block-wrap">
                                <pre class="code-block" id="prompt-code">${esc(agent.prompt(path))}</pre>
                                <button class="copy-btn" data-copy-target="prompt-code">Copy</button>
                            </div>
                        `}
                    </div>

                    <div class="howto-substep">
                        <div class="howto-substep-label">iii. Edit your goals <span class="text-secondary text-xs">(optional)</span></div>
                        <p class="text-secondary text-sm mb-2">
                            ${isSetup
                                ? 'The curator scores posts against this file. Leave it blank and the agent will interview you on first run.'
                                : 'Once your workspace is set up, you can edit preferences here.'}
                        </p>
                        ${isSetup ? `
                            <textarea id="goals-textarea" class="goals-textarea" rows="10" spellcheck="false">${esc((this.goals && this.goals.content) || '')}</textarea>
                            <div class="flex items-center gap-2 mt-2">
                                <button class="btn btn-primary btn-sm" id="goals-save">Save goals</button>
                                <span class="text-secondary text-sm" id="goals-status"></span>
                            </div>
                        ` : ''}
                    </div>

                    <div class="howto-substep">
                        <div class="howto-substep-label">iv. View the curated feed</div>
                        <p class="text-secondary text-sm">
                            Open <a href="#curated">AI Curation</a> — the freshly-filtered pack appears with per-post scores and reasons.
                        </p>
                    </div>
                </div>
            </div>
        `;
    },

    _stepShip() {
        return `
            <div class="howto-step">
                <div class="howto-step-num">4</div>
                <div class="howto-step-body">
                    <h3 class="font-semibold text-subtitle mb-2">Take it with you <span class="text-secondary text-sm">(optional)</span></h3>
                    <p class="text-secondary text-sm">
                        Right-click the pack folder in Finder → <em>Compress</em>. AirDrop the zip to your phone. Open the Focus Lab Feed viewer in Safari and import the zip.
                        <br><br>
                        The viewer is a single HTML file — it runs entirely in the browser, no server, no account. Scroll position is saved per pack, so you can pick up where you left off.
                    </p>
                </div>
            </div>
        `;
    },

    // ---- Helpers ----

    _packFullPath() {
        const ws = this.workspace && this.workspace.path || '';
        if (!this.selectedPack) return ws;
        return `${ws}/exports/${this.selectedPack}`;
    },

    _refreshCommands() {
        const agent = this.agents.find(a => a.id === this.selectedAgent);
        const path = this._packFullPath();
        const l = document.getElementById('launch-code');
        const p = document.getElementById('prompt-code');
        if (l) l.textContent = agent.launchCmd(path);
        if (p) p.textContent = agent.prompt(path);
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
        const target = document.getElementById(btn.dataset.copyTarget);
        if (!target) return;
        try {
            await navigator.clipboard.writeText(target.textContent);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        } catch (e) {
            const range = document.createRange();
            range.selectNode(target);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            document.execCommand('copy');
            window.getSelection().removeAllRanges();
        }
    },
};

// helpers
function quote(path) {
    if (!path) return '.';
    return path.includes(' ') ? `"${path}"` : path;
}
function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
function escAttr(s) { return esc(s); }

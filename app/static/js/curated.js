/**
 * Curated Feed page — shares the Viewer's post layout (same classes, same
 * read-more / carousel / stats markup) and layers curator-specific bits on
 * top: a pack selector, category filter chips, score pill + filter_reason
 * per post, and a collapsed audit log of dropped posts.
 *
 * Helpers (formatText, timeAgo, fmtNum, renderPostBody, toggleReadMore,
 * setupVideoAutoplay, setupCarouselDrag, openLightbox) are borrowed from
 * ViewerPage so the two pages stay pixel-identical.
 */
(function () {
'use strict';

window.CuratedPage = {
    packs: [],                  // {name, kept, dropped_count, ...}
    selectedPack: null,         // pack metadata currently being shown
    filterData: null,           // { filter_metadata, posts } for selected pack
    activeCategory: 'all',

    render() {
        return `
            <div class="fade-in">
                <div class="page-header">
                    <h1 class="page-title">Curated Feed</h1>
                    <select id="curated-pack-selector" onchange="CuratedPage.onPackSelect(this.value)">
                        <option value="">Loading…</option>
                    </select>
                </div>
                <div id="curated-body"></div>
            </div>
        `;
    },

    async init() {
        try {
            const data = await api('/curated/packs');
            this.packs = data.packs || [];
            this.renderPackSelector();
            if (this.packs.length > 0) {
                await this.loadPack(this.packs[0].name);
            } else {
                this.renderEmpty(data.is_setup);
            }
        } catch (e) {
            document.getElementById('curated-body').innerHTML =
                `<div class="card text-danger">Failed to load curated packs: ${esc(e.message)}</div>`;
        }
    },

    renderPackSelector() {
        const sel = document.getElementById('curated-pack-selector');
        if (!sel) return;
        if (this.packs.length === 0) {
            sel.innerHTML = '<option value="">No curated packs</option>';
            sel.disabled = true;
            return;
        }
        sel.innerHTML = this.packs.map(p => {
            const when = p.filtered_at ? new Date(p.filtered_at).toLocaleString() : '';
            return `<option value="${escAttr(p.name)}">${esc(p.name)} — ${p.kept} kept${when ? ' · ' + when : ''}</option>`;
        }).join('');
        sel.disabled = false;
    },

    renderEmpty(isSetup) {
        const body = document.getElementById('curated-body');
        if (!body) return;
        if (!isSetup) {
            body.innerHTML = `
                <div class="card">
                    <h3 class="font-semibold text-subtitle mb-2">Workspace not set up</h3>
                    <p class="text-secondary text-sm mb-3">
                        Pick a workspace folder first (Export page), then come back after you've
                        exported and curated a pack.
                    </p>
                    <a href="#export" class="btn btn-primary">Go to Export</a>
                </div>
            `;
            return;
        }
        body.innerHTML = `
            <div class="card">
                <h3 class="font-semibold text-subtitle mb-2">No curated packs yet</h3>
                <p class="text-secondary text-sm mb-3">
                    Export a pack, then run your agent against it — when it writes
                    <code>posts.filtered.json</code> in the pack folder, it'll show up here.
                </p>
                <div class="flex gap-2">
                    <a href="#export" class="btn btn-secondary">Export</a>
                    <a href="#curate" class="btn btn-primary">AI Curation</a>
                </div>
            </div>
        `;
    },

    async onPackSelect(name) {
        if (!name) return;
        await this.loadPack(name);
    },

    async loadPack(name) {
        const body = document.getElementById('curated-body');
        body.innerHTML = '<div class="empty-state"><p class="text-secondary">Loading pack…</p></div>';
        try {
            this.filterData = await api(`/curated/packs/${encodeURIComponent(name)}`);
            this.selectedPack = this.packs.find(p => p.name === name) || { name };
            this.activeCategory = 'all';
            this.renderFeed();
        } catch (e) {
            body.innerHTML = `<div class="card text-danger">Failed to load pack: ${esc(e.message)}</div>`;
        }
    },

    renderFeed() {
        const body = document.getElementById('curated-body');
        const meta = (this.filterData && this.filterData.filter_metadata) || {};
        const posts = (this.filterData && this.filterData.posts) || [];
        const dropped = meta.dropped || [];
        const cc = meta.category_counts || {};

        const chip = (cat, label, count) => `
            <button class="btn btn-ghost btn-pill btn-sm ${this.activeCategory === cat ? 'active' : ''}"
                    data-chip="${cat}"
                    onclick="CuratedPage.setCategory('${cat}')">
                ${label}${typeof count === 'number' ? ` <span class="chip-count">${count}</span>` : ''}
            </button>
        `;

        body.innerHTML = `
            <div class="curated-meta">
                <div class="curated-meta-item"><strong>${posts.length}</strong> kept</div>
                ${meta.dropped_count ? `<div class="curated-meta-item text-secondary">${meta.dropped_count} dropped</div>` : ''}
                ${meta.median_score != null ? `<div class="curated-meta-item text-secondary">median score ${meta.median_score}</div>` : ''}
                ${meta.drop_rule ? `<div class="curated-meta-item text-secondary"><code>${esc(meta.drop_rule)}</code></div>` : ''}
                ${meta.filtered_at ? `<div class="curated-meta-item text-secondary">${new Date(meta.filtered_at).toLocaleString()}</div>` : ''}
            </div>

            <div class="sort-bar" id="curated-chips">
                ${chip('all', 'All', posts.length)}
                ${chip('goal', 'Goal', cc.goal)}
                ${chip('joy', 'Joy', cc.joy)}
                ${chip('adjacent', 'Adjacent', cc.adjacent)}
                ${chip('neutral', 'Neutral', cc.neutral)}
            </div>

            <div id="curated-feed">
                ${posts.map(p => this.renderPost(p)).join('') || '<div class="empty-state"><p class="text-secondary">No kept posts.</p></div>'}
            </div>

            ${dropped.length > 0 ? `
                <details class="dropped-log">
                    <summary>${dropped.length} dropped posts (audit log)</summary>
                    <table class="dropped-table">
                        <thead><tr><th>Score</th><th>Category</th><th>ID</th><th>Reason</th></tr></thead>
                        <tbody>
                            ${dropped.map(d => `
                                <tr>
                                    <td>${d.score ?? '—'}</td>
                                    <td><span class="badge badge-${escAttr(d.category || 'neutral')}">${esc(d.category || '')}</span></td>
                                    <td><code>${esc(d.id || '')}</code></td>
                                    <td>${esc(d.filter_reason || '')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </details>
            ` : ''}
        `;

        // Set up video autoplay (local — ViewerPage's is scoped to #viewer-feed).
        if (this._videoObserver) this._videoObserver.disconnect();
        const videos = document.querySelectorAll('#curated-feed video');
        if (videos.length) {
            this._videoObserver = new IntersectionObserver((entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) entry.target.play().catch(() => {});
                    else entry.target.pause();
                }
            }, { threshold: 0.5 });
            videos.forEach(v => this._videoObserver.observe(v));
        }
        // Carousel drag — borrow (class-based, not id-based).
        if (window.ViewerPage && ViewerPage.setupCarouselDrag) ViewerPage.setupCarouselDrag();

        this.applyCategoryFilter();
    },

    toggleReason(postId, btn) {
        const el = document.getElementById(`reason-${postId}`);
        if (!el) return;
        const isHidden = el.classList.toggle('hidden');
        if (btn) btn.textContent = isHidden ? 'why' : 'hide';
    },

    setCategory(cat) {
        this.activeCategory = cat;
        const chips = document.querySelectorAll('#curated-chips [data-chip]');
        chips.forEach(btn => btn.classList.toggle('active', btn.dataset.chip === cat));
        this.applyCategoryFilter();
    },

    applyCategoryFilter() {
        const feed = document.getElementById('curated-feed');
        if (!feed) return;
        const cat = this.activeCategory;
        feed.querySelectorAll('.post').forEach(el => {
            el.style.display = (cat === 'all' || el.dataset.category === cat) ? '' : 'none';
        });
    },

    // ---- renderPost: uses Viewer's class names/structure so the two pages
    // share one visual language. Curator-specific bits (score pill, category
    // badge, filter_reason) are layered on top.
    renderPost(post) {
        const V = window.ViewerPage;  // reuse helpers
        const platform = post.platform || 'twitter';
        const plinks = (V && V.PLATFORM_LINKS[platform]) || null;
        const authorDisplay = esc(post.author_name || post.author_handle || 'Unknown');
        const handleDisplay = post.author_handle
            ? `<span class="post-handle">${plinks ? `<a href="${plinks.mention(post.author_handle)}" target="_blank" rel="noopener">@${esc(post.author_handle)}</a>` : '@' + esc(post.author_handle)}</span>`
            : '';
        const postId = esc(post.id || Math.random().toString(36).slice(2));

        // Score pill + category badge — placed top-right of post header.
        const scoreHtml = typeof post.score === 'number'
            ? `<span class="score-pill score-${scoreBucket(post.score)}">${post.score}</span>` : '';
        const categoryHtml = post.category
            ? `<span class="badge badge-${escAttr(post.category)}">${esc(post.category)}</span>` : '';

        // Filter reason — hidden by default; toggled from a button in the stats row.
        const reasonBody = post.filter_reason
            ? `<div class="filter-reason hidden" id="reason-${postId}">${esc(post.filter_reason)}</div>` : '';
        const reasonToggle = post.filter_reason
            ? `<button class="reason-toggle" onclick="CuratedPage.toggleReason('${postId}', this)">why</button>` : '';

        // Body with read-more (borrow Viewer's implementation).
        const bodyHtml = V && V.renderPostBody
            ? V.renderPostBody(post.text, platform, postId)
            : `<div class="post-body">${esc(post.text || '')}</div>`;

        // Media resolution — pack-scoped URLs.
        const packName = this.selectedPack ? this.selectedPack.name : '';
        const mediaHtml = renderMedia(post, packName);

        // Repost + ad badges + quoted post — match Viewer's conventions.
        const repostBadge = post.is_repost
            ? `<div class="repost-label">${platform === 'twitter' ? 'Retweeted' : 'Reposted'} by @${esc(post.original_author || 'unknown')}</div>` : '';
        const adBadge = post.is_ad ? '<span class="badge-ad">Ad</span>' : '';
        const showPlatformBadge = true;  // always show on curated (since feed mixes platforms)

        let quotedHtml = '';
        if (post.quoted_post) {
            const qp = post.quoted_post;
            const qpLinks = plinks;
            quotedHtml = `<div class="quoted-post">
                <div class="quoted-post-header">
                    <span class="font-semibold text-sm">${esc(qp.author_name || qp.author_handle || 'Unknown')}</span>
                    ${qp.author_handle ? `<span class="post-handle text-xs">${qpLinks ? `<a href="${qpLinks.mention(qp.author_handle)}" target="_blank" rel="noopener">@${esc(qp.author_handle)}</a>` : '@' + esc(qp.author_handle)}</span>` : ''}
                </div>
                ${qp.text ? `<div class="text-sm" style="line-height:1.4;margin-top:4px">${V && V.formatText ? V.formatText(qp.text, platform) : esc(qp.text)}</div>` : ''}
            </div>`;
        }

        const repostLabel = platform === 'twitter' ? 'RT' : 'reposts';
        const timeAgo = V && V.timeAgo ? V.timeAgo(post.created_at) : (post.created_at || '');
        const fmtNum = V && V.fmtNum ? V.fmtNum.bind(V) : (n => String(n || 0));

        return `<div class="post" data-category="${escAttr(post.category || 'neutral')}" data-id="${postId}">
            ${repostBadge}
            <div class="post-header">
                <div>
                    ${adBadge}
                    ${showPlatformBadge ? `<span class="badge badge-${platform} mr-2">${platform}</span>` : ''}
                    <span class="post-author">${authorDisplay}</span>
                    ${handleDisplay}
                </div>
                <span class="post-time">
                    ${categoryHtml}
                    ${scoreHtml}
                    ${post.url ? `<a href="${escAttr(post.url)}" target="_blank" rel="noopener">${timeAgo}</a>` : timeAgo}
                </span>
            </div>
            ${bodyHtml}
            ${mediaHtml}
            ${quotedHtml}
            <div class="post-stats">
                <span>replies ${fmtNum(post.replies)}</span>
                <span>${repostLabel} ${fmtNum(post.reposts)}</span>
                <span>likes ${fmtNum(post.likes)}</span>
                ${post.quotes ? `<span>quotes ${fmtNum(post.quotes)}</span>` : ''}
                ${reasonToggle}
            </div>
            ${reasonBody}
        </div>`;
    },
};

// ---- helpers ----

function renderMedia(post, packName) {
    const paths = post.local_media_paths || [];
    const fallbacks = [...(post.media_urls || []), ...(post.video_urls || [])];
    const count = Math.max(paths.length, fallbacks.length);
    if (count === 0) return '';

    const base = packName ? `/api/curated/packs/${encodeURIComponent(packName)}/` : '';
    const resolve = (path, fallback) => {
        if (path && path.startsWith('media/')) return base + path;
        return fallback || path || '';
    };

    if (count === 1) {
        const src = resolve(paths[0], fallbacks[0]);
        return `<div class="post-media">${mediaElement(src, paths[0])}</div>`;
    }

    // Carousel — matches Viewer's .post-carousel .post-carousel-item classes.
    const slides = [];
    for (let i = 0; i < count; i++) {
        const src = resolve(paths[i], fallbacks[i]);
        slides.push(`<div class="post-carousel-item">${mediaElement(src, paths[i])}<span class="post-carousel-badge">${i + 1}/${count}</span></div>`);
    }
    return `<div class="post-carousel viewer-carousel">${slides.join('')}</div>`;
}

function mediaElement(src, hintPath) {
    if (!src) return '<div class="empty-state">Media unavailable</div>';
    const lower = (hintPath || src).toLowerCase();
    const isVideo = /\.(mp4|mov|m4v|webm)(\?|$)/.test(lower) || lower.includes('_v0') || lower.includes('_v1');
    if (isVideo) return `<video src="${escAttr(src)}" muted loop preload="metadata" controls></video>`;
    return `<img src="${escAttr(src)}" loading="lazy" onclick="ViewerPage.openLightbox && ViewerPage.openLightbox(this.src)">`;
}

function scoreBucket(n) {
    if (n >= 80) return 'high';
    if (n >= 60) return 'mid';
    if (n >= 40) return 'low';
    return 'verylow';
}

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return esc(s); }

})();

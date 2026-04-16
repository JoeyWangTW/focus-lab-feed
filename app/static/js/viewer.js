/**
 * Viewer Page — feed viewer ported from viewer.html
 */
window.ViewerPage = {
    allPosts: [],
    currentSort: 'time',
    currentPlatform: 'all',
    availableRuns: [],

    PLATFORM_LINKS: {
        twitter:   { mention: h => `https://x.com/${h}`, hashtag: h => `https://x.com/hashtag/${h}` },
        threads:   { mention: h => `https://threads.net/@${h}`, hashtag: h => `https://threads.net/search?q=%23${h}` },
        instagram: { mention: h => `https://instagram.com/${h}`, hashtag: h => `https://instagram.com/explore/tags/${h}` },
        youtube:   { mention: h => `https://youtube.com/@${h}`, hashtag: h => `https://youtube.com/results?search_query=%23${h}` },
    },

    render() {
        return `
            <div class="fade-in">
                <div class="page-header">
                    <h1 class="page-title">Viewer</h1>
                    <select id="run-selector" onchange="ViewerPage.onRunSelect(this.value)">
                        <option value="latest">Latest runs</option>
                    </select>
                </div>
                <div id="viewer-meta" class="viewer-meta"></div>
                <div class="tabs" id="viewer-platform-tabs"></div>
                <div class="sort-bar" id="viewer-sort-bar">
                    <button class="btn btn-ghost btn-pill btn-sm active" data-sort="time" onclick="ViewerPage.setSort('time',this)">Latest</button>
                    <button class="btn btn-ghost btn-pill btn-sm" data-sort="likes" onclick="ViewerPage.setSort('likes',this)">Most Liked</button>
                    <button class="btn btn-ghost btn-pill btn-sm" data-sort="reposts" onclick="ViewerPage.setSort('reposts',this)">Most Reposted</button>
                    <button class="btn btn-ghost btn-pill btn-sm" data-sort="replies" onclick="ViewerPage.setSort('replies',this)">Most Replies</button>
                </div>
                <div id="viewer-feed"></div>
            </div>
        `;
    },

    async init() {
        await this.loadLatest();
    },

    async loadLatest() {
        try {
            const data = await api('/data/runs/latest');
            this.allPosts = [];

            for (const [platform, runData] of Object.entries(data.runs || {})) {
                const posts = (runData.posts || []).map(p => ({
                    ...p,
                    platform: p.platform || platform,
                    reposts: p.reposts ?? p.retweets ?? 0,
                    is_repost: p.is_repost ?? p.is_retweet ?? false,
                }));
                this.allPosts.push(...posts);
            }

            // Load available runs for dropdown (grouped by date)
            const runsData = await api('/data/runs');
            this.availableDates = runsData.dates || [];
            this.availableRuns = (runsData.runs || []).filter(r => r.has_posts);
            this.renderRunSelector();

            if (this.allPosts.length > 0) {
                this.renderAll();
            } else {
                document.getElementById('viewer-feed').innerHTML = `
                    <div class="empty-state">
                        <div class="icon">&#9776;</div>
                        <p>No collected feeds yet</p>
                        <p class="text-sm mt-2">Go to <a href="#collect">Collect</a> to start gathering feeds</p>
                    </div>
                `;
            }
        } catch (e) {
            document.getElementById('viewer-feed').innerHTML =
                `<div class="text-danger" style="padding:20px">Failed to load: ${e.message}</div>`;
        }
    },

    renderRunSelector() {
        const sel = document.getElementById('run-selector');
        let html = '<option value="latest">Latest runs</option>';

        // Group by date using optgroup
        if (this.availableDates && this.availableDates.length > 0) {
            for (const dateGroup of this.availableDates) {
                html += `<optgroup label="${dateGroup.date}">`;
                for (const job of dateGroup.jobs) {
                    for (const run of job.platforms) {
                        if (!run.has_posts) continue;
                        const label = `${run.platform || '?'} — job ${job.job_id} (${run.post_count || '?'} posts)`;
                        html += `<option value="${run.run_id}">${label}</option>`;
                    }
                }
                html += '</optgroup>';
            }
        } else {
            // Fallback for flat list
            for (const run of this.availableRuns) {
                const label = `${run.platform || '?'} — ${run.timestamp || run.run_id} (${run.post_count || '?'} posts)`;
                html += `<option value="${run.run_id}">${label}</option>`;
            }
        }

        sel.innerHTML = html;
    },

    async onRunSelect(value) {
        if (value === 'latest') {
            await this.loadLatest();
            return;
        }

        try {
            const data = await api(`/data/runs/${value}`);
            const posts = (data.posts || data.tweets || []).map(p => ({
                ...p,
                reposts: p.reposts ?? p.retweets ?? 0,
                is_repost: p.is_repost ?? p.is_retweet ?? false,
            }));
            this.allPosts = posts;
            this.renderAll();
        } catch (e) {
            document.getElementById('viewer-feed').innerHTML =
                `<div class="text-danger" style="padding:20px">Failed to load run: ${e.message}</div>`;
        }
    },

    renderAll() {
        this.currentPlatform = 'all';
        this.currentSort = 'time';
        this.renderPlatformTabs();
        this.updateMeta();
        this.renderPosts();
    },

    renderPlatformTabs() {
        const platforms = [...new Set(this.allPosts.map(p => p.platform))];
        const counts = {};
        for (const p of this.allPosts) counts[p.platform] = (counts[p.platform] || 0) + 1;

        const tabs = document.getElementById('viewer-platform-tabs');
        let html = `<button class="tab active" data-platform="all" onclick="ViewerPage.setPlatform('all',this)">All<span class="badge badge-count">${this.allPosts.length}</span></button>`;
        for (const p of platforms) {
            html += `<button class="tab" data-platform="${p}" onclick="ViewerPage.setPlatform('${p}',this)">${p.charAt(0).toUpperCase() + p.slice(1)}<span class="badge badge-count">${counts[p]}</span></button>`;
        }
        tabs.innerHTML = html;
        tabs.style.display = platforms.length > 1 ? 'flex' : 'none';
    },

    setPlatform(platform, btn) {
        this.currentPlatform = platform;
        document.querySelectorAll('#viewer-platform-tabs .tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.updateMeta();
        this.renderPosts();
    },

    setSort(sort, btn) {
        this.currentSort = sort;
        document.querySelectorAll('#viewer-sort-bar button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.renderPosts();
    },

    renderPostBody(text, platform, postId) {
        const TRUNCATE_LEN = 300;
        const formatted = this.formatText(text, platform);
        if (!text || text.length <= TRUNCATE_LEN) {
            return `<div class="post-body">${formatted}</div>`;
        }
        // Truncate at word boundary
        const truncated = text.substring(0, TRUNCATE_LEN).replace(/\s+\S*$/, '');
        const truncatedFormatted = this.formatText(truncated, platform);
        return `<div class="post-body">
            <span id="post-short-${postId}">${truncatedFormatted}… <button class="read-more-btn" onclick="ViewerPage.toggleReadMore('${postId}')">Read more</button></span>
            <span id="post-full-${postId}" class="hidden">${formatted} <button class="read-more-btn" onclick="ViewerPage.toggleReadMore('${postId}')">Show less</button></span>
        </div>`;
    },

    toggleReadMore(postId) {
        const short = document.getElementById(`post-short-${postId}`);
        const full = document.getElementById(`post-full-${postId}`);
        if (!short || !full) return;
        short.classList.toggle('hidden');
        full.classList.toggle('hidden');
    },

    getFilteredPosts() {
        if (this.currentPlatform === 'all') return this.allPosts;
        return this.allPosts.filter(p => p.platform === this.currentPlatform);
    },

    updateMeta() {
        const posts = this.getFilteredPosts();
        const imgCount = posts.reduce((n, t) => n + (t.media_urls || []).length, 0);
        const vidCount = posts.reduce((n, t) => n + (t.video_urls || []).length, 0);
        const platforms = [...new Set(posts.map(p => p.platform))].join(', ');
        document.getElementById('viewer-meta').textContent =
            `${posts.length} posts | ${imgCount} images, ${vidCount} videos | ${platforms}`;
    },

    formatText(text, platform) {
        const links = this.PLATFORM_LINKS[platform] || this.PLATFORM_LINKS.twitter;
        return (text || '')
            .replace(/&amp;/g, '&')
            .replace(/(https?:\/\/t\.co\/\S+)/g, '')
            .replace(/(https?:\/\/\S+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
            .replace(/@(\w+)/g, (_, h) => `<a href="${links.mention(h)}" target="_blank" rel="noopener">@${h}</a>`)
            .replace(/#(\w+)/g, (_, h) => `<a href="${links.hashtag(h)}" target="_blank" rel="noopener">#${h}</a>`)
            .trim();
    },

    timeAgo(dateStr) {
        if (!dateStr) return '';
        // YouTube returns relative strings like "3 years ago" — pass through as-is
        if (/\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago/i.test(dateStr)) return dateStr;
        // Also handle "Streamed X ago", "Updated X ago" etc.
        if (/ago$/i.test(dateStr)) return dateStr;
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr; // fallback: show raw text rather than "Invalid Date"
        const diff = (Date.now() - d) / 1000;
        if (diff < 60) return `${Math.floor(diff)}s`;
        if (diff < 3600) return `${Math.floor(diff/60)}m`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },

    fmtNum(n) {
        n = n || 0;
        if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n/1000).toFixed(1) + 'K';
        return n.toString();
    },

    sortPosts(posts, sort) {
        const sorted = [...posts];
        switch(sort) {
            case 'likes': sorted.sort((a,b) => (b.likes||0) - (a.likes||0)); break;
            case 'reposts': sorted.sort((a,b) => (b.reposts||0) - (a.reposts||0)); break;
            case 'replies': sorted.sort((a,b) => (b.replies||0) - (a.replies||0)); break;
            default: sorted.sort((a,b) => new Date(b.created_at) - new Date(a.created_at));
        }
        return sorted;
    },

    renderPosts() {
        const posts = this.getFilteredPosts();
        const sorted = this.sortPosts(posts, this.currentSort);
        const feed = document.getElementById('viewer-feed');

        if (sorted.length === 0) {
            feed.innerHTML = '<div class="empty-state">No posts to display</div>';
            return;
        }

        feed.innerHTML = sorted.map(t => {
            const platform = t.platform || 'twitter';
            const plinks = this.PLATFORM_LINKS[platform] || this.PLATFORM_LINKS.twitter;
            const authorDisplay = t.author_name || t.author_handle || 'Unknown';
            const handleDisplay = t.author_handle
                ? `<span class="post-handle"><a href="${plinks.mention(t.author_handle)}" target="_blank" rel="noopener">@${t.author_handle}</a></span>`
                : '';
            const showPlatformBadge = this.currentPlatform === 'all' && this.allPosts.some(p => p.platform !== platform);

            let mediaHtml = '';
            const pd = t.platform_data || {};
            if (platform === 'youtube' && pd.embed_url) {
                mediaHtml = `<div class="post-embed"><iframe src="${pd.embed_url}" allowfullscreen loading="lazy"></iframe></div>`;
            } else {
                const paths = (t.local_media_paths || []);
                if (paths.length === 1) {
                    const fullPath = paths[0].startsWith('feed_data/') ? '/' + paths[0] : '/feed_data/' + paths[0];
                    if (paths[0].endsWith('.mp4')) {
                        mediaHtml = `<div class="post-media"><video src="${fullPath}" muted loop preload="metadata" controls></video></div>`;
                    } else {
                        mediaHtml = `<div class="post-media"><img src="${fullPath}" loading="lazy" onclick="ViewerPage.openLightbox(this.src)"></div>`;
                    }
                } else if (paths.length >= 2) {
                    const items = paths.map((p, idx) => {
                        const fullPath = p.startsWith('feed_data/') ? '/' + p : '/feed_data/' + p;
                        if (p.endsWith('.mp4')) {
                            return `<div class="post-carousel-item"><video src="${fullPath}" muted loop preload="metadata" controls></video><span class="post-carousel-badge">${idx+1}/${paths.length}</span></div>`;
                        } else {
                            return `<div class="post-carousel-item"><img src="${fullPath}" loading="lazy" onclick="ViewerPage.openLightbox(this.src)"><span class="post-carousel-badge">${idx+1}/${paths.length}</span></div>`;
                        }
                    });
                    mediaHtml = `<div class="post-carousel viewer-carousel">${items.join('')}</div>`;
                }
            }

            const repostBadge = t.is_repost ? `<div class="repost-label">${platform === 'twitter' ? 'Retweeted' : 'Reposted'} by @${t.original_author || 'unknown'}</div>` : '';
            const repostLabel = platform === 'twitter' ? 'RT' : 'reposts';
            const adBadge = t.is_ad ? '<span class="badge-ad">Ad</span>' : '';
            const hasReplies = t.top_replies && t.top_replies.length > 0;
            const postId = t.id || Math.random().toString(36).substr(2);
            const shortBadge = pd.type === 'short' ? '<span class="badge-short">Short</span>' : '';

            // Quoted/original post embed
            let quotedHtml = '';
            if (t.quoted_post) {
                const qp = t.quoted_post;
                const qpLinks = this.PLATFORM_LINKS[platform] || this.PLATFORM_LINKS.twitter;
                quotedHtml = `<div class="quoted-post">
                    <div class="quoted-post-header">
                        <span class="font-semibold text-sm">${qp.author_name || qp.author_handle || 'Unknown'}</span>
                        ${qp.author_handle ? `<span class="post-handle text-xs"><a href="${qpLinks.mention(qp.author_handle)}" target="_blank" rel="noopener">@${qp.author_handle}</a></span>` : ''}
                    </div>
                    ${qp.text ? `<div class="text-sm" style="line-height:1.4;margin-top:4px">${this.formatText(qp.text, platform)}</div>` : ''}
                </div>`;
            }

            return `<div class="post">
                ${repostBadge}
                <div class="post-header">
                    <div>
                        ${adBadge}
                        ${showPlatformBadge ? `<span class="badge badge-${platform} mr-2">${platform}</span>` : ''}
                        <span class="post-author">${authorDisplay}</span>
                        ${handleDisplay}${shortBadge}
                    </div>
                    <span class="post-time">${t.url ? `<a href="${t.url}" target="_blank" rel="noopener">${this.timeAgo(t.created_at)}</a>` : this.timeAgo(t.created_at)}</span>
                </div>
                ${this.renderPostBody(t.text, platform, postId)}
                ${mediaHtml}
                ${quotedHtml}
                <div class="post-stats">
                    <span>replies ${this.fmtNum(t.replies)}${hasReplies ? '<span class="has-replies"></span>' : ''}</span>
                    <span>${repostLabel} ${this.fmtNum(t.reposts)}</span>
                    <span>likes ${this.fmtNum(t.likes)}</span>
                    ${t.quotes ? `<span>quotes ${this.fmtNum(t.quotes)}</span>` : ''}
                </div>
                ${hasReplies ? `
                <button class="post-replies-toggle" onclick="ViewerPage.toggleReplies('${postId}',this)">Show ${t.top_replies.length} replies</button>
                <div id="replies-${postId}" class="post-replies-section hidden">
                    ${t.top_replies.map(r => `
                        <div class="reply">
                            <div class="mb-1">
                                <span class="reply-author">${r.author_name || r.author_handle || 'Unknown'}</span>
                                <span class="reply-handle">${r.author_handle ? `@${r.author_handle}` : ''}</span>
                            </div>
                            <div class="reply-body">${this.formatText(r.text, platform)}</div>
                            <div class="reply-stats">${this.fmtNum(r.likes)} likes</div>
                        </div>
                    `).join('')}
                </div>` : ''}
            </div>`;
        }).join('');

        this.setupCarouselDrag();
        this.setupVideoAutoplay();
    },

    toggleReplies(postId, btn) {
        const section = document.getElementById(`replies-${postId}`);
        if (!section) return;
        const isOpen = !section.classList.contains('hidden');
        section.classList.toggle('hidden');
        const count = section.children.length;
        btn.textContent = isOpen ? `Show ${count} replies` : 'Hide replies';
    },

    openLightbox(src) {
        const lb = document.createElement('div');
        lb.className = 'lightbox';
        lb.innerHTML = `<button class="lightbox-close">&times;</button><img src="${src}">`;
        lb.onclick = () => lb.remove();
        document.body.appendChild(lb);
    },

    setupVideoAutoplay() {
        // Disconnect previous observer if any
        if (this._videoObserver) this._videoObserver.disconnect();

        const videos = document.querySelectorAll('#viewer-feed video');
        if (videos.length === 0) return;

        this._videoObserver = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                const video = entry.target;
                if (entry.isIntersecting) {
                    video.play().catch(() => {});
                } else {
                    video.pause();
                }
            }
        }, { threshold: 0.5 });

        videos.forEach(v => this._videoObserver.observe(v));
    },

    setupCarouselDrag() {
        document.querySelectorAll('.viewer-carousel').forEach(carousel => {
            let isDown = false, startX, scrollLeft, hasDragged = false;
            carousel.addEventListener('mousedown', e => {
                isDown = true; hasDragged = false;
                startX = e.pageX - carousel.offsetLeft;
                scrollLeft = carousel.scrollLeft;
            });
            carousel.addEventListener('mouseleave', () => { isDown = false; });
            carousel.addEventListener('mouseup', () => { isDown = false; });
            carousel.addEventListener('mousemove', e => {
                if (!isDown) return;
                e.preventDefault();
                const x = e.pageX - carousel.offsetLeft;
                const walk = (x - startX) * 1.5;
                if (Math.abs(walk) > 5) hasDragged = true;
                carousel.scrollLeft = scrollLeft - walk;
            });
            carousel.addEventListener('click', e => {
                if (hasDragged) { e.stopPropagation(); e.preventDefault(); }
            }, true);
        });
    },
};

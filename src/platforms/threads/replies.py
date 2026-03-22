"""Reply capture for Threads — opens post pages in parallel tabs and extracts from DOM."""

import asyncio
from dataclasses import dataclass


@dataclass
class Reply:
    id: str
    text: str
    author_handle: str
    author_name: str
    created_at: str = ""
    likes: int = 0


async def _extract_replies_from_dom(page, op_username: str, max_replies: int = 5) -> list[Reply]:
    """Extract reply data from the rendered DOM of a Threads post page."""
    raw_replies = await page.evaluate('''(opUsername) => {
        const results = [];
        const allLinks = [...document.querySelectorAll("a[role='link']")];
        const profilePattern = /^\\/@[\\w.]+$/;

        const profileLinks = allLinks.filter(a => {
            const href = a.getAttribute('href') || '';
            return profilePattern.test(href) && a.textContent.trim().length > 0;
        });

        let skippedOp = false;
        for (const link of profileLinks) {
            const username = (link.getAttribute('href') || '').replace('/@', '');
            const displayName = link.textContent.trim();

            // Skip the original poster (first occurrence)
            if (!skippedOp && username === opUsername) {
                skippedOp = true;
                continue;
            }
            // Skip logged-in user profile link
            if (displayName === 'Profile') continue;

            let container = link;
            for (let i = 0; i < 8; i++) {
                container = container.parentElement;
                if (!container) break;

                const spans = container.querySelectorAll('span[dir="auto"]');
                for (const span of spans) {
                    const text = span.textContent.trim();
                    if (text.length > 3 && text !== displayName && text !== username
                        && !text.includes('View activity') && !text.includes('views')
                        && !text.includes('Like') && !text.includes('Reply')
                        && !text.startsWith('@')) {
                        results.push({username, displayName, text: text.substring(0, 500)});
                        break;
                    }
                }
                if (results.length > 0 && results[results.length-1].username === username) break;
            }
        }
        return results;
    }''', op_username)

    replies = []
    seen = set()
    for r in raw_replies:
        if r["username"] in seen or r["username"] == op_username:
            continue
        seen.add(r["username"])
        replies.append(Reply(
            id=r["username"],  # No ID available from DOM
            text=r["text"],
            author_handle=r["username"],
            author_name=r["displayName"],
        ))
        if len(replies) >= max_replies:
            break

    return replies


async def _fetch_replies_for_post(
    context, post_id: str, post_url: str, op_username: str, max_replies: int = 5
) -> list[Reply]:
    """Open a new tab, navigate to a post, extract replies from DOM."""
    page = await context.new_page()
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(8000)
        return await _extract_replies_from_dom(page, op_username, max_replies)
    except Exception as e:
        print(f"[replies:threads] Error fetching {post_url}: {e}")
        return []
    finally:
        await page.close()


async def fetch_replies(
    context,
    posts: list[dict],
    max_replies_per_post: int = 5,
    batch_size: int = 3,
) -> dict[str, list[Reply]]:
    """Fetch replies for multiple posts using parallel tabs."""
    all_replies: dict[str, list[Reply]] = {}

    post_tasks = []
    for p in posts:
        url = p.get("url", "")
        pid = p.get("id", "")
        author = p.get("author_handle", "")
        if url and pid:
            post_tasks.append((pid, url, author))

    total = len(post_tasks)
    print(f"[replies:threads] Fetching replies for {total} posts (batch_size={batch_size})")

    for i in range(0, total, batch_size):
        batch = post_tasks[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"[replies:threads] Batch {batch_num}: opening {len(batch)} tabs...")

        tasks = [
            _fetch_replies_for_post(context, pid, url, author, max_replies_per_post)
            for pid, url, author in batch
        ]
        results = await asyncio.gather(*tasks)

        for (pid, url, author), replies in zip(batch, results):
            all_replies[pid] = replies
            if replies:
                print(f"[replies:threads]   {pid}: {len(replies)} replies captured")

    total_replies = sum(len(r) for r in all_replies.values())
    posts_with = sum(1 for r in all_replies.values() if r)
    print(f"[replies:threads] Done: {total_replies} replies from {posts_with}/{total} posts")

    return all_replies

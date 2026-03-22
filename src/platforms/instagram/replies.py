"""Comment capture for Instagram — opens post pages in parallel tabs."""

import asyncio
import json
import re
from dataclasses import asdict, dataclass


@dataclass
class Reply:
    id: str
    text: str
    author_handle: str
    author_name: str
    created_at: str
    likes: int = 0


COMMENT_CONNECTION_KEY = "xdt_api__v1__media__media_id__comments__connection"


def _extract_comments_from_html(html: str, max_comments: int = 5) -> list[Reply]:
    """Extract comments from Instagram post page HTML script tags."""
    replies = []
    scripts = re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )

    for script_content in scripts:
        if "comment_like_count" not in script_content:
            continue
        try:
            data = json.loads(script_content)
            _find_comments(data, replies, max_comments)
        except (json.JSONDecodeError, TypeError):
            continue

        if len(replies) >= max_comments:
            break

    return replies[:max_comments]


def _find_comments(obj, replies: list, max_count: int, depth: int = 0):
    """Recursively search for comment edges in parsed JSON."""
    if depth > 15 or len(replies) >= max_count:
        return

    if isinstance(obj, dict):
        # Check for comment connection
        conn = obj.get(COMMENT_CONNECTION_KEY)
        if conn and isinstance(conn, dict):
            for edge in conn.get("edges", []):
                if len(replies) >= max_count:
                    return
                node = edge.get("node", {})
                if node.get("__typename") == "XDTCommentDict":
                    user = node.get("user", {})
                    replies.append(Reply(
                        id=str(node.get("pk", "")),
                        text=node.get("text", ""),
                        author_handle=user.get("username", ""),
                        author_name=user.get("full_name", user.get("username", "")),
                        created_at=str(node.get("created_at", "")),
                        likes=node.get("comment_like_count", 0),
                    ))
            return

        for v in obj.values():
            _find_comments(v, replies, max_count, depth + 1)

    elif isinstance(obj, list):
        for v in obj[:20]:
            _find_comments(v, replies, max_count, depth + 1)


async def _fetch_comments_for_post(
    context, post_id: str, post_url: str, max_comments: int = 5
) -> list[Reply]:
    """Open a new tab, navigate to a post, extract comments from HTML."""
    page = await context.new_page()
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(6000)

        html = await page.content()
        replies = _extract_comments_from_html(html, max_comments)
        return replies
    except Exception as e:
        print(f"[replies:instagram] Error fetching {post_url}: {e}")
        return []
    finally:
        await page.close()


async def fetch_replies(
    context,
    posts: list[dict],
    max_replies_per_post: int = 5,
    batch_size: int = 3,
) -> dict[str, list[Reply]]:
    """Fetch comments for multiple posts using parallel tabs."""
    all_replies: dict[str, list[Reply]] = {}

    post_tasks = []
    for p in posts:
        url = p.get("url", "")
        pid = p.get("id", "")
        if url and pid:
            post_tasks.append((pid, url))

    total = len(post_tasks)
    print(f"[replies:instagram] Fetching comments for {total} posts (batch_size={batch_size})")

    for i in range(0, total, batch_size):
        batch = post_tasks[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"[replies:instagram] Batch {batch_num}: opening {len(batch)} tabs...")

        tasks = [
            _fetch_comments_for_post(context, pid, url, max_replies_per_post)
            for pid, url in batch
        ]
        results = await asyncio.gather(*tasks)

        for (pid, url), replies in zip(batch, results):
            all_replies[pid] = replies
            if replies:
                print(f"[replies:instagram]   {pid}: {len(replies)} comments captured")

    total_replies = sum(len(r) for r in all_replies.values())
    posts_with = sum(1 for r in all_replies.values() if r)
    print(f"[replies:instagram] Done: {total_replies} comments from {posts_with}/{total} posts")

    return all_replies

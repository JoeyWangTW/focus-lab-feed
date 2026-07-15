"""Shared resilience helpers for reply/comment capture.

Reply fetching opens detail-page tabs in parallel. Any single tab can hang —
a navigation that never settles, a comments response that never arrives, or a
`page.close()` that stalls on an overloaded browser. Left unbounded, one hung
tab freezes the whole `asyncio.gather` batch, which in turn stalls the
collector before it ever saves its scraped posts. These helpers put a hard
ceiling on every tab so a stuck one is abandoned, never fatal.
"""

from __future__ import annotations

import asyncio

# goto (15s) + settle (6-8s) + margin. A tab that exceeds this is abandoned.
PER_TAB_TIMEOUT = 35
# Even closing a tab can hang on a wedged browser; cap it so cancellation can't stall.
CLOSE_TIMEOUT = 5

# Whole-phase ceilings the collectors wrap around media/reply work. Enrichment
# that blows past these is abandoned so the run still finishes and saves.
MEDIA_PHASE_TIMEOUT = 420   # media can be legitimately large; per-file cap is separate
REPLY_PHASE_TIMEOUT = 180


async def safe_close(page) -> None:
    """Close a page without ever hanging the caller."""
    try:
        await asyncio.wait_for(page.close(), timeout=CLOSE_TIMEOUT)
    except Exception:
        pass


async def bounded_tab(coro, label: str, timeout: int = PER_TAB_TIMEOUT):
    """Await one reply-tab coroutine with a hard timeout.

    Returns [] instead of raising or hanging, so `gather` over a batch always
    completes even if individual tabs wedge.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[replies] tab abandoned after {timeout}s: {label}")
        return []
    except Exception as e:  # noqa: BLE001 — a bad tab must never sink the batch
        print(f"[replies] tab error {label}: {type(e).__name__}: {e}")
        return []

"""GraphQL response interception and parsing."""

import json
import re
from datetime import datetime
from pathlib import Path


class ResponseInterceptor:
    """Intercepts and stores Twitter GraphQL API responses."""

    GRAPHQL_PATTERN = re.compile(r"/i/api/graphql/.*/Home")

    def __init__(self, output_dir: str = "feed_data"):
        self.responses: list[dict] = []
        self.output_dir = Path(output_dir)

    async def handle_response(self, response):
        """Callback for page.on('response') — captures matching GraphQL responses."""
        if not self.GRAPHQL_PATTERN.search(response.url):
            return

        try:
            body = await response.json()
            endpoint = response.url.split("/")[-1].split("?")[0]
            status = response.status

            self.responses.append(body)

            # Save raw response for debugging
            today = datetime.now().strftime("%Y-%m-%d")
            raw_dir = self.output_dir / today / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%H%M%S")
            raw_path = raw_dir / f"{endpoint}_{timestamp}.json"
            raw_path.write_text(json.dumps(body, indent=2))

            # Count tweet entries
            tweet_count = self._count_entries(body)
            size = len(json.dumps(body))

            print(
                f"[interceptor] {endpoint} | status={status} | "
                f"size={size:,}B | entries={tweet_count}"
            )

        except Exception as e:
            print(f"[interceptor] Error processing response: {e}")

    def _count_entries(self, body: dict) -> int:
        """Count tweet entries in a GraphQL response."""
        try:
            instructions = (
                body.get("data", {})
                .get("home", {})
                .get("home_timeline_urt", {})
                .get("instructions", [])
            )
            count = 0
            for instruction in instructions:
                entries = instruction.get("entries", [])
                count += len(entries)
            return count
        except (AttributeError, TypeError):
            return 0

"""Lightweight web search helpers for learning resources."""

from __future__ import annotations

import html
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str


class DuckDuckGoHTMLParser(HTMLParser):
    """Extract result links and snippets from DuckDuckGo's HTML endpoint."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_link = False
        self._in_snippet = False
        self._current_title: list[str] = []
        self._current_url = ""
        self._pending_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        class_name = attributes.get("class", "")
        if tag == "a" and ("result__a" in class_name or "result-link" in class_name):
            self._in_link = True
            self._current_title = []
            self._current_url = self._clean_url(attributes.get("href", "") or "")
        elif "result__snippet" in class_name or "result-snippet" in class_name:
            self._in_snippet = True
            self._pending_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False
        elif self._in_snippet:
            self._in_snippet = False
            title = self._clean_text("".join(self._current_title))
            snippet = self._clean_text("".join(self._pending_snippet))
            if title and self._current_url:
                self.results.append(SearchResult(title=title, url=self._current_url, snippet=snippet))
            self._current_title = []
            self._current_url = ""
            self._pending_snippet = []

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._current_title.append(data)
        elif self._in_snippet:
            self._pending_snippet.append(data)

    def _clean_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(html.unescape(url))
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return query["uddg"][0]
        return html.unescape(url)

    def _clean_text(self, value: str) -> str:
        return " ".join(html.unescape(value).split())


class WebSearchClient:
    """Search public web resources without requiring an extra API key."""

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        encoded_query = urllib.parse.urlencode({"q": query})
        request = urllib.request.Request(
            f"https://lite.duckduckgo.com/lite/?{encoded_query}",
            headers={"User-Agent": "Mozilla/5.0 VisionCraft-Aura/0.1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")

        parser = DuckDuckGoHTMLParser()
        parser.feed(body)
        return parser.results[:limit]

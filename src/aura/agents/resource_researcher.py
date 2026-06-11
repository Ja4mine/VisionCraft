"""Find learning resources to ground generated plans."""

from __future__ import annotations

from dataclasses import dataclass

from aura.core.web_search import SearchResult, WebSearchClient


@dataclass(frozen=True, slots=True)
class ResourceBundle:
    """Search queries and the results found for them."""

    queries: list[str]
    results: list[SearchResult]

    def to_markdown_context(self) -> str:
        if not self.results:
            return "未检索到可用资料。"

        lines = ["以下是生成计划时可引用的公开学习资料："]
        for index, result in enumerate(self.results, start=1):
            lines.append(f"{index}. [{result.title}]({result.url})")
            if result.snippet:
                lines.append(f"   - 摘要：{result.snippet}")
        return "\n".join(lines)


class ResourceResearcher:
    """Search for safe, learning-oriented public resources."""

    def __init__(self, search_client: WebSearchClient | None = None) -> None:
        self.search_client = search_client or WebSearchClient()

    def research(self, goal: str, summary: str, per_query_limit: int = 3) -> ResourceBundle:
        queries = self._build_queries(goal=goal, summary=summary)
        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for query in queries:
            for result in self.search_client.search(query, limit=per_query_limit):
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)

        return ResourceBundle(queries=queries, results=results)

    def _build_queries(self, goal: str, summary: str) -> list[str]:
        text = f"{goal}\n{summary}".lower()
        queries = [
            "Windows Internals learning path official resources",
            "Microsoft Learn Windows system programming C++",
            "Practical Malware Analysis learning resources legal lab",
            "MITRE ATT&CK command and control detection techniques",
            "Sigma rules detection engineering getting started",
            "YARA rules malware analysis learning",
            "TryHackMe SOC detection engineering windows internals",
            "Hack The Box Academy windows privilege escalation fundamentals",
        ]

        if "macos" in text or "mac os" in text:
            queries.extend(
                [
                    "Apple Platform Security macOS security official guide",
                    "Objective-See macOS security tools learning",
                ]
            )
        if "c++" in text or "cpp" in text:
            queries.append("C++ network programming learning resources")
        if "python" in text:
            queries.append("Python for cybersecurity defensive automation learning resources")

        return queries[:10]

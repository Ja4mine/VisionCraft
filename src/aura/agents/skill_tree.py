"""Skill tree generation and terminal rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from rich.console import Console
from rich.tree import Tree


SKILL_TREE_SYSTEM_PROMPT = """
你是 Aura 的技能树建模器。
请把学习计划转换为有向无环图 DAG，用于游戏化学习进度展示。

要求：
1. 只返回 JSON，不要 Markdown，不要代码块。
2. nodes 至少 6 个，最多 20 个。
3. status 只能是 completed、in_progress、locked。
4. 至少一个节点为 in_progress；未满足依赖的节点为 locked。
5. edges 必须表达先修依赖，不能形成循环。
6. 如果涉及红队、安全攻防、C2、免杀、持久化，只用安全学习表述，例如系统原理、检测工程、授权实验室实践，不输出攻击步骤。

JSON 格式：
{
  "nodes": [
    {"id": "n1", "name": "Windows 进程与线程基础", "status": "in_progress"}
  ],
  "edges": [
    {"from": "n1", "to": "n2"}
  ]
}
""".strip()


@dataclass(frozen=True, slots=True)
class SkillNode:
    """One node in the skill DAG."""

    id: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class SkillEdge:
    """One dependency edge in the skill DAG."""

    source: str
    target: str


@dataclass(frozen=True, slots=True)
class SkillTreeGraph:
    """Skill DAG data structure."""

    nodes: list[SkillNode]
    edges: list[SkillEdge]

    def to_json(self) -> str:
        return json.dumps(
            {
                "nodes": [
                    {"id": node.id, "name": node.name, "status": node.status}
                    for node in self.nodes
                ],
                "edges": [
                    {"from": edge.source, "to": edge.target}
                    for edge in self.edges
                ],
            },
            ensure_ascii=False,
            indent=2,
        )


class SkillTreeError(RuntimeError):
    """Raised when a skill tree cannot be generated or parsed."""


class SkillTreeGenerator:
    """Generate a skill DAG from a Markdown plan."""

    def __init__(self, client: OpenAI, model: str, temperature: float = 0.2) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature

    def generate(self, plan_markdown: str) -> SkillTreeGraph:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SKILL_TREE_SYSTEM_PROMPT},
                {"role": "user", "content": plan_markdown},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise SkillTreeError("DeepSeek 返回了空技能树。")
        return parse_skill_tree(content)


def parse_skill_tree(raw_json: str) -> SkillTreeGraph:
    """Parse and validate skill-tree JSON."""

    try:
        payload: dict[str, Any] = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SkillTreeError(f"技能树 JSON 不合法：{raw_json}") from exc

    nodes = [
        SkillNode(
            id=str(node["id"]),
            name=str(node["name"]),
            status=_normalize_status(str(node.get("status", "locked"))),
        )
        for node in payload.get("nodes", [])
        if "id" in node and "name" in node
    ]
    node_ids = {node.id for node in nodes}
    edges = [
        SkillEdge(source=str(edge["from"]), target=str(edge["to"]))
        for edge in payload.get("edges", [])
        if str(edge.get("from")) in node_ids and str(edge.get("to")) in node_ids
    ]
    if not nodes:
        raise SkillTreeError("技能树必须至少包含一个节点。")
    return SkillTreeGraph(nodes=nodes, edges=edges)


class SkillTreeRenderer:
    """Render a skill tree graph in the terminal."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def render(self, graph: SkillTreeGraph) -> None:
        roots = self._root_ids(graph)
        children = self._children_map(graph)
        node_map = {node.id: node for node in graph.nodes}
        tree = Tree("[bold]Aura Skill Tree[/bold]")
        visited: set[str] = set()

        for root_id in roots:
            self._add_node(tree, root_id, node_map, children, visited)

        for node in graph.nodes:
            if node.id not in visited:
                self._add_node(tree, node.id, node_map, children, visited)

        self.console.print(tree)

    def _add_node(
        self,
        parent: Tree,
        node_id: str,
        node_map: dict[str, SkillNode],
        children: dict[str, list[str]],
        visited: set[str],
    ) -> None:
        if node_id in visited or node_id not in node_map:
            return
        visited.add(node_id)
        node = node_map[node_id]
        branch = parent.add(self._label(node))
        for child_id in children.get(node_id, []):
            self._add_node(branch, child_id, node_map, children, visited)

    def _label(self, node: SkillNode) -> str:
        if node.status == "completed":
            return f"[green][✓] {node.name}[/green]"
        if node.status == "in_progress":
            return f"[bold blue][~] {node.name}[/bold blue]"
        return f"[dim][ ] {node.name}[/dim]"

    def _root_ids(self, graph: SkillTreeGraph) -> list[str]:
        targets = {edge.target for edge in graph.edges}
        return [node.id for node in graph.nodes if node.id not in targets]

    def _children_map(self, graph: SkillTreeGraph) -> dict[str, list[str]]:
        children: dict[str, list[str]] = {}
        for edge in graph.edges:
            children.setdefault(edge.source, []).append(edge.target)
        return children


def _normalize_status(status: str) -> str:
    if status in {"completed", "in_progress", "locked"}:
        return status
    return "locked"

"""LLM-backed dual-mode topology generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI


GoalType = Literal["learning_divergent", "task_convergent"]
NodeStatus = Literal["completed", "in_progress", "pending", "locked"]


TOPOLOGY_GENERATOR_SYSTEM_PROMPT = """
你是 Aura 的双模式目标拓扑引擎。
你的任务是先判断用户目标类型，再生成对应拓扑结构。

你必须只返回 JSON，不要 Markdown，不要代码块，不要额外解释。

JSON Schema 必须严格符合：
{
  "goal_type": "learning_divergent" 或 "task_convergent",
  "rationale": "解释为什么将该目标归类为此类型...",
  "nodes": [
    {"id": "n1", "name": "节点名称", "status": "pending", "energy_level": 3}
  ],
  "edges": [
    {"from": "n1", "to": "n2"}
  ]
}

意图识别规则：
1. learning_divergent：目标是“学习某个领域/建立知识体系/长期探索能力”，通常没有唯一交付物。
2. task_convergent：目标是“完成某个项目/交付某个成果/上线某个系统/通过某个明确验收”，必须有唯一最终交付物。

拓扑生成规则：
1. 如果 goal_type 是 learning_divergent：
   - 生成发散树状图，方向是从根基础能力指向多个分支。
   - 根节点应该是总基础或入门能力。
   - 允许多个叶子节点代表并行探索方向。
   - 示例：密码学基础 -> 群论 / 椭圆曲线 -> Bulletproofs / Adaptor Signatures。
2. 如果 goal_type 是 task_convergent：
   - 生成收束依赖管道，多条前置分支必须最终汇聚到唯一 Terminal Node。
   - Terminal Node 必须是唯一没有 outgoing edge 的节点。
   - Terminal Node 名称必须是明确最终交付物，例如“完成云服务期末项目部署”。
   - 所有节点必须存在通向 Terminal Node 的路径。
3. nodes 至少 5 个，最多 18 个。
4. edges 必须构成 DAG，不能循环。
5. status 只能是 completed、in_progress、pending、locked。
6. energy_level 必须是 1-5 的整数。
7. 如果涉及红队、C2、攻击性程序、免杀、持久化、漏洞利用或恶意软件相关内容，必须使用安全学习表述：系统原理、检测工程、授权实验室、防御验证、遥测分析；不要输出真实攻击、规避检测、隐蔽持久化或恶意投放步骤。
""".strip()


@dataclass(frozen=True, slots=True)
class TopologyNode:
    """One node in a goal topology graph."""

    id: str
    name: str
    status: NodeStatus
    energy_level: int


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    """One directed dependency edge."""

    source: str
    target: str


@dataclass(frozen=True, slots=True)
class GoalTopology:
    """Dual-mode topology graph."""

    goal_type: GoalType
    rationale: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]

    def to_json(self) -> str:
        return json.dumps(
            {
                "goal_type": self.goal_type,
                "rationale": self.rationale,
                "nodes": [
                    {
                        "id": node.id,
                        "name": node.name,
                        "status": node.status,
                        "energy_level": node.energy_level,
                    }
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


class TopologyError(RuntimeError):
    """Raised when topology generation or validation fails."""


class TopologyGenerator:
    """Generate a learning-divergent or task-convergent topology from a plan."""

    def __init__(self, client: OpenAI, model: str, temperature: float = 0.2) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature

    def generate(self, goal: str, plan_markdown: str) -> GoalTopology:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": TOPOLOGY_GENERATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请根据原始目标和学习计划生成双模式拓扑 JSON。\n\n"
                        f"原始目标：\n{goal}\n\n"
                        f"计划内容：\n{plan_markdown}"
                    ),
                },
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise TopologyError("DeepSeek 返回了空拓扑。")
        return parse_topology(content)


def parse_topology(raw_json: str) -> GoalTopology:
    """Parse and validate topology JSON."""

    try:
        payload: dict[str, Any] = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise TopologyError(f"拓扑 JSON 不合法：{raw_json}") from exc

    goal_type = _normalize_goal_type(str(payload.get("goal_type", "")))
    nodes = _parse_nodes(payload.get("nodes", []))
    node_ids = {node.id for node in nodes}
    edges = [
        TopologyEdge(source=str(edge["from"]), target=str(edge["to"]))
        for edge in payload.get("edges", [])
        if str(edge.get("from")) in node_ids and str(edge.get("to")) in node_ids
    ]

    if not nodes:
        raise TopologyError("拓扑必须至少包含一个节点。")
    _validate_acyclic(nodes, edges)
    if goal_type == "task_convergent":
        _validate_single_terminal(nodes, edges)

    return GoalTopology(
        goal_type=goal_type,
        rationale=str(payload.get("rationale", "")).strip(),
        nodes=nodes,
        edges=edges,
    )


def _parse_nodes(raw_nodes: Any) -> list[TopologyNode]:
    nodes: list[TopologyNode] = []
    if not isinstance(raw_nodes, list):
        return nodes

    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id", f"n{index}")).strip() or f"n{index}"
        name = str(raw_node.get("name", "")).strip()
        if not name:
            continue
        nodes.append(
            TopologyNode(
                id=node_id,
                name=name,
                status=_normalize_status(str(raw_node.get("status", "pending"))),
                energy_level=_normalize_energy(raw_node.get("energy_level", 3)),
            )
        )
    return nodes


def _normalize_goal_type(value: str) -> GoalType:
    if value == "task_convergent":
        return "task_convergent"
    return "learning_divergent"


def _normalize_status(value: str) -> NodeStatus:
    if value in {"completed", "in_progress", "pending", "locked"}:
        return value  # type: ignore[return-value]
    return "pending"


def _normalize_energy(value: Any) -> int:
    try:
        energy = int(value)
    except (TypeError, ValueError):
        return 3
    return min(max(energy, 1), 5)


def _validate_acyclic(nodes: list[TopologyNode], edges: list[TopologyEdge]) -> None:
    node_ids = {node.id for node in nodes}
    visiting: set[str] = set()
    visited: set[str] = set()
    children: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        children.setdefault(edge.source, []).append(edge.target)

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise TopologyError("拓扑不能包含循环依赖。")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id in children.get(node_id, []):
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)


def _validate_single_terminal(nodes: list[TopologyNode], edges: list[TopologyEdge]) -> None:
    sources = {edge.source for edge in edges}
    terminal_ids = [node.id for node in nodes if node.id not in sources]
    if len(terminal_ids) != 1:
        raise TopologyError("交付型任务必须有且只有一个最终交付节点。")

    reverse_edges: dict[str, list[str]] = {}
    for edge in edges:
        reverse_edges.setdefault(edge.target, []).append(edge.source)

    reachable: set[str] = set()

    def walk_backward(node_id: str) -> None:
        if node_id in reachable:
            return
        reachable.add(node_id)
        for parent_id in reverse_edges.get(node_id, []):
            walk_backward(parent_id)

    walk_backward(terminal_ids[0])
    if reachable != {node.id for node in nodes}:
        raise TopologyError("交付型任务的所有节点都必须能汇聚到最终交付节点。")

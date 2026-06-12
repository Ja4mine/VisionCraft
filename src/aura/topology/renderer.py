"""Rich renderers for dual-mode Aura topologies."""

from __future__ import annotations

from collections import deque

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from aura.topology.generator import GoalTopology, TopologyEdge, TopologyNode


class TopologyRenderer:
    """Render learning-divergent trees and task-convergent pipelines."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def render(self, topology: GoalTopology) -> None:
        if topology.goal_type == "task_convergent":
            self.render_task_pipeline(topology)
            return
        self.render_learning_tree(topology)

    def render_learning_tree(self, topology: GoalTopology) -> None:
        """Render a divergent knowledge tree with rich.tree."""

        children = self._children_map(topology.edges)
        node_map = {node.id: node for node in topology.nodes}
        roots = self._root_ids(topology)
        root = Tree("[bold]🌱 Learning Topology[/bold]")
        if topology.rationale:
            root.add(f"[dim]{topology.rationale}[/dim]")

        visited: set[str] = set()
        for root_id in roots:
            self._add_learning_node(root, root_id, node_map, children, visited)

        for node in topology.nodes:
            if node.id not in visited:
                self._add_learning_node(root, node.id, node_map, children, visited)

        self.console.print(root)

    def render_task_pipeline(self, topology: GoalTopology) -> None:
        """Render a convergent dependency pipeline for delivery-focused goals."""

        stages = self._convergent_stages(topology)
        terminal = self._terminal_node(topology)

        table = Table(
            title="Milestone Pipeline",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold magenta",
        )
        table.add_column("Stage", justify="center", style="bold")
        table.add_column("Converging Work", ratio=3)
        table.add_column("Flow", justify="center")

        max_stage = max(stages.keys(), default=0)
        for stage_index in range(max_stage + 1):
            nodes = stages.get(stage_index, [])
            if terminal and stage_index == max_stage:
                nodes = [terminal]
            table.add_row(
                f"T-{max_stage - stage_index}" if stage_index < max_stage else "FINAL",
                self._format_stage_nodes(nodes, highlight_final=stage_index == max_stage),
                "   ↓\n   ↓\n   ↓" if stage_index < max_stage else "  🎯",
            )

        summary = Panel(
            Group(
                Text("多个前置分支正在向唯一交付物收束。", style="bold"),
                Text(topology.rationale or "该目标被识别为交付型任务。", style="dim"),
            ),
            title="Task-Convergent Topology",
            border_style="yellow",
        )
        self.console.print(summary)
        self.console.print(table)

    def _add_learning_node(
        self,
        parent: Tree,
        node_id: str,
        node_map: dict[str, TopologyNode],
        children: dict[str, list[str]],
        visited: set[str],
    ) -> None:
        if node_id in visited or node_id not in node_map:
            return
        visited.add(node_id)
        node = node_map[node_id]
        branch = parent.add(self._node_label(node))
        for child_id in children.get(node_id, []):
            self._add_learning_node(branch, child_id, node_map, children, visited)

    def _format_stage_nodes(self, nodes: list[TopologyNode], highlight_final: bool = False) -> str:
        if not nodes:
            return "[dim]No explicit milestone[/dim]"
        lines: list[str] = []
        for node in nodes:
            label = self._node_label(node, plain=False)
            if highlight_final:
                label = f"[bold reverse yellow] {node.name} [/bold reverse yellow] [dim]energy:{node.energy_level}[/dim]"
            lines.append(label)
        return "\n".join(lines)

    def _node_label(self, node: TopologyNode, plain: bool = False) -> str:
        prefix = {
            "completed": "[✓]",
            "in_progress": "[~]",
            "pending": "[ ]",
            "locked": "[🔒]",
        }.get(node.status, "[ ]")
        text = f"{prefix} {node.name} [energy:{node.energy_level}]"
        if plain:
            return text
        if node.status == "completed":
            return f"[green]{text}[/green]"
        if node.status == "in_progress":
            return f"[bold blue]{text}[/bold blue]"
        if node.status == "locked":
            return f"[dim]{text}[/dim]"
        return text

    def _root_ids(self, topology: GoalTopology) -> list[str]:
        targets = {edge.target for edge in topology.edges}
        return [node.id for node in topology.nodes if node.id not in targets]

    def _children_map(self, edges: list[TopologyEdge]) -> dict[str, list[str]]:
        children: dict[str, list[str]] = {}
        for edge in edges:
            children.setdefault(edge.source, []).append(edge.target)
        return children

    def _terminal_node(self, topology: GoalTopology) -> TopologyNode | None:
        sources = {edge.source for edge in topology.edges}
        terminals = [node for node in topology.nodes if node.id not in sources]
        return terminals[0] if terminals else None

    def _convergent_stages(self, topology: GoalTopology) -> dict[int, list[TopologyNode]]:
        terminal = self._terminal_node(topology)
        if terminal is None:
            return {0: topology.nodes}

        reverse_edges: dict[str, list[str]] = {}
        for edge in topology.edges:
            reverse_edges.setdefault(edge.target, []).append(edge.source)

        node_map = {node.id: node for node in topology.nodes}
        distance_to_terminal: dict[str, int] = {terminal.id: 0}
        queue: deque[str] = deque([terminal.id])

        while queue:
            node_id = queue.popleft()
            for parent_id in reverse_edges.get(node_id, []):
                next_distance = distance_to_terminal[node_id] + 1
                if parent_id not in distance_to_terminal or next_distance > distance_to_terminal[parent_id]:
                    distance_to_terminal[parent_id] = next_distance
                    queue.append(parent_id)

        max_distance = max(distance_to_terminal.values(), default=0)
        stages: dict[int, list[TopologyNode]] = {}
        for node_id, distance in distance_to_terminal.items():
            stage_index = max_distance - distance
            stages.setdefault(stage_index, []).append(node_map[node_id])

        for nodes in stages.values():
            nodes.sort(key=lambda node: (node.status != "in_progress", node.energy_level, node.name))
        return stages

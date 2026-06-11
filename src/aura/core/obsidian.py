"""Export VisionCraft plans into an Obsidian vault."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aura.storage.state_manager import StoredLearningPlan


@dataclass(frozen=True, slots=True)
class ObsidianExportResult:
    """Paths written during an Obsidian export."""

    note_path: Path
    index_path: Path


class ObsidianExporter:
    """Write plans as Obsidian notes with frontmatter and an index page."""

    def __init__(self, vault_path: Path, folder: str = "VisionCraft") -> None:
        self.vault_path = vault_path.expanduser()
        self.folder = folder.strip().strip("/") or "VisionCraft"
        self.root = self.vault_path / self.folder
        self.plans_dir = self.root / "Plans"
        self.index_path = self.root / "VisionCraft Plan Index.md"

    def export_plan(
        self,
        plan: StoredLearningPlan,
        all_plans: list[StoredLearningPlan],
    ) -> ObsidianExportResult:
        self._ensure_ready()
        note_path = self.plans_dir / self._note_filename(plan)
        note_path.write_text(self._build_plan_note(plan), encoding="utf-8")
        self.write_index(all_plans)
        return ObsidianExportResult(note_path=note_path, index_path=self.index_path)

    def export_all(self, plans: list[StoredLearningPlan]) -> list[ObsidianExportResult]:
        self._ensure_ready()
        results: list[ObsidianExportResult] = []
        for plan in plans:
            note_path = self.plans_dir / self._note_filename(plan)
            note_path.write_text(self._build_plan_note(plan), encoding="utf-8")
            results.append(ObsidianExportResult(note_path=note_path, index_path=self.index_path))
        self.write_index(plans)
        return results

    def write_index(self, plans: list[StoredLearningPlan]) -> None:
        self._ensure_ready()
        self.index_path.write_text(self._build_index(plans), encoding="utf-8")

    def _ensure_ready(self) -> None:
        if not self.vault_path.exists():
            raise ValueError(f"Obsidian vault 不存在：{self.vault_path}")
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def _build_plan_note(self, plan: StoredLearningPlan) -> str:
        frontmatter = "\n".join(
            [
                "---",
                f'title: "{self._escape_yaml(plan.title)}"',
                "type: visioncraft-plan",
                f"plan_id: {plan.id}",
                f"status: {plan.status}",
                f"category: {plan.category}",
                f"priority: {plan.priority}",
                f"importance: {plan.importance}",
                f'goal: "{self._escape_yaml(plan.goal)}"',
                f'source_path: "{self._escape_yaml(str(plan.output_path))}"',
                f"updated: {datetime.now().isoformat(timespec='seconds')}",
                "tags:",
                "  - visioncraft",
                "  - learning-plan",
                f"  - visioncraft/{self._slug(plan.category)}",
                "---",
                "",
            ]
        )
        backlinks = (
            f"> [!info] VisionCraft Metadata\n"
            f"> 分类：`{plan.category}` | 优先级：`{plan.priority}` | 重要性：`{plan.importance}` | 状态：`{plan.status}`\n"
            f"> 索引：[[VisionCraft Plan Index]]\n\n"
        )
        return frontmatter + backlinks + plan.markdown.strip() + "\n"

    def _build_index(self, plans: list[StoredLearningPlan]) -> str:
        sorted_plans = sorted(plans, key=lambda plan: (-plan.importance, plan.priority, plan.title))
        lines = [
            "---",
            "type: visioncraft-index",
            "tags:",
            "  - visioncraft",
            "  - index",
            f"updated: {datetime.now().isoformat(timespec='seconds')}",
            "---",
            "",
            "# VisionCraft Plan Index",
            "",
            "## Plans By Priority",
            "",
            "| 计划 | 分类 | 状态 | 优先级 | 重要性 |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for plan in sorted_plans:
            note_name = self._note_filename(plan).removesuffix(".md")
            lines.append(
                f"| [[{note_name}|{plan.title}]] | {plan.category} | {plan.status} | {plan.priority} | {plan.importance} |"
            )

        lines.extend(
            [
                "",
                "## Dataview",
                "",
                "```dataview",
                'TABLE category AS "分类", status AS "状态", priority AS "优先级", importance AS "重要性"',
                f'FROM "{self.folder}/Plans"',
                'WHERE type = "visioncraft-plan"',
                "SORT importance DESC, priority ASC",
                "```",
                "",
                "## 分类说明",
                "",
                "- `priority`: 1 最高，5 最低，表示执行顺序。",
                "- `importance`: 1 最低，5 最高，表示长期价值。",
                "- 可以直接编辑计划笔记 frontmatter 中的 `category`、`priority`、`importance`。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _note_filename(self, plan: StoredLearningPlan) -> str:
        return f"{plan.id:04d}_{self._slug(plan.title)}.md"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", value.strip().lower())
        return slug.strip("_")[:80] or "plan"

    def _escape_yaml(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

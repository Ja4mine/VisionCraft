"""Daily tracker helpers for energy-aware check-ins."""

from __future__ import annotations

from dataclasses import dataclass

from aura.agents.scheduler import SchedulerDecision


@dataclass(frozen=True, slots=True)
class DailyTaskBrief:
    """A task shown to the user during daily check-in."""

    task_id: int
    title: str
    sequence_day: int
    energy_level: int


def decision_to_markdown(decision: SchedulerDecision) -> str:
    """Render a scheduler decision as a compact Markdown summary."""

    lines = [
        f"**{decision.welcome_message}**",
        "",
        f"- 当前序列：Sequence Day {decision.current_sequence}",
        f"- 调整说明：{decision.adjustment_summary or '按当前状态继续。'}",
        "",
        "### 今日建议任务",
    ]
    if not decision.recommended_tasks:
        lines.append("- 今天先做 10 分钟计划回顾或环境整理，让状态重新启动。")
        return "\n".join(lines)

    for task in decision.recommended_tasks:
        lines.append(
            f"- [ ] #{task.task_id} Sequence Day {task.sequence_day} | "
            f"energy_level: {task.energy_level} | {task.title}"
        )
    return "\n".join(lines)

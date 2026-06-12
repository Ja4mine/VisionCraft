"""Human-centric scheduling for guilt-free daily learning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


RESCHEDULER_SYSTEM_PROMPT = """
你是 Aura 的人性化学习调度状态机。
你的职责不是批评用户，而是在用户回来时静默重排学习序列。

核心原则：
1. 绝对不要使用“逾期”“落后”“拖延”“失败”等带评价色彩的措辞。
2. 任务不绑定自然日期，只绑定 Sequence Day。用户回来时，从 current_sequence 继续。
3. 如果 missed_days > 0，把积压内容降级、拆小或平摊到未来序列，不要要求用户补偿过去。
4. 输出一句温暖、去评价化的欢迎语，例如“欢迎回来，我们接着从上次的地方开始。”
5. 根据 energy_level 只选择不超过用户今日精力值的任务。
6. 如果任务涉及红队、C2、免杀、持久化或攻击性程序，只能安排授权实验室、防御研究、检测工程、系统原理学习，不给真实攻击或规避步骤。

你必须只返回 JSON：
{
  "welcome_message": "欢迎回来，我们接着从上次的地方开始。",
  "current_sequence": 3,
  "adjustment_summary": "今天只保留低到中等认知负荷任务，并把高负荷内容平摊到后续序列。",
  "recommended_tasks": [
    {"task_id": 1, "title": "复盘 Windows 进程与线程基础", "sequence_day": 3, "energy_level": 2, "reason": "符合今日精力"}
  ]
}
""".strip()


@dataclass(frozen=True, slots=True)
class SchedulerTask:
    """A task candidate from the sequence-based task pool."""

    task_id: int
    title: str
    sequence_day: int
    energy_level: int


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    """AI scheduling decision for today's check-in."""

    welcome_message: str
    current_sequence: int
    adjustment_summary: str
    recommended_tasks: list[SchedulerTask]


class SchedulerError(RuntimeError):
    """Raised when scheduling cannot produce valid structured output."""


class HumanCentricScheduler:
    """Use the LLM as a gentle scheduling state machine."""

    def __init__(self, client: OpenAI, model: str, temperature: float = 0.2) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature

    def reschedule(
        self,
        missed_days: int,
        current_sequence: int,
        energy_level: int,
        task_pool: list[SchedulerTask],
    ) -> SchedulerDecision:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": RESCHEDULER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "missed_days": missed_days,
                            "current_sequence": current_sequence,
                            "today_energy_level": energy_level,
                            "task_pool": [
                                {
                                    "task_id": task.task_id,
                                    "title": task.title,
                                    "sequence_day": task.sequence_day,
                                    "energy_level": task.energy_level,
                                }
                                for task in task_pool
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise SchedulerError("DeepSeek 返回了空调度结果。")
        return self._parse_decision(content)

    @staticmethod
    def fallback_decision(
        missed_days: int,
        current_sequence: int,
        energy_level: int,
        task_pool: list[SchedulerTask],
    ) -> SchedulerDecision:
        selected = [
            task
            for task in task_pool
            if task.sequence_day >= current_sequence and task.energy_level <= energy_level
        ][:3]
        welcome = "欢迎回来，我们接着从上次的地方开始。"
        summary = "今天先选择与你当前精力匹配的任务，高负荷内容会自然顺延。"
        if missed_days == 0:
            welcome = "今天也从一个合适的小步开始。"
            summary = "按当前序列继续推进。"
        return SchedulerDecision(
            welcome_message=welcome,
            current_sequence=current_sequence,
            adjustment_summary=summary,
            recommended_tasks=selected,
        )

    def _parse_decision(self, raw_content: str) -> SchedulerDecision:
        try:
            payload: dict[str, Any] = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise SchedulerError(f"调度器未返回合法 JSON：{raw_content}") from exc

        tasks: list[SchedulerTask] = []
        for raw_task in payload.get("recommended_tasks", []):
            tasks.append(
                SchedulerTask(
                    task_id=int(raw_task.get("task_id", 0)),
                    title=str(raw_task.get("title", "")).strip(),
                    sequence_day=int(raw_task.get("sequence_day", payload.get("current_sequence", 1))),
                    energy_level=int(raw_task.get("energy_level", 3)),
                )
            )

        return SchedulerDecision(
            welcome_message=str(payload.get("welcome_message", "欢迎回来，我们接着从上次的地方开始。")).strip(),
            current_sequence=int(payload.get("current_sequence", 1)),
            adjustment_summary=str(payload.get("adjustment_summary", "")).strip(),
            recommended_tasks=tasks,
        )

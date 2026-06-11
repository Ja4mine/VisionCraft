"""Daily tracking and plan adjustment agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openai import OpenAI


TRACKER_SYSTEM_PROMPT = """
你是 VisionCraft Aura 的每日学习追踪器。
你的任务是读取用户当前计划、今日打卡、最近进度和学习习惯，然后输出一份调整后的完整 Markdown 学习计划。

你必须遵守：
1. 只输出 Markdown，不要输出 JSON，不要包裹代码块。
2. 保留原计划中仍然合理的长期目标、资料来源和验收标准。
3. 根据今日完成情况动态调整后续 3-7 天任务：完成顺利则小幅推进，遇到阻碍则降级、拆小、增加补基础任务。
4. 如果用户连续未完成或能量低，必须降低每日负担并给出低摩擦恢复任务。
5. 如果目标涉及红队、C2、攻击性程序、免杀、持久化、漏洞利用或恶意软件相关内容，必须限定为授权实验室、CTF、靶场、防御研究、检测工程和安全架构学习；不要提供真实目标攻击、免杀绕过、隐蔽持久化、恶意代码投放、规避检测或未授权入侵步骤。

Markdown 结构必须包含：
# <计划标题>
## 今日复盘
## 调整决策
## 更新后的接下来 7 天
## 保留的长期路线
## 风险与降级规则
## 下次打卡关注点
""".strip()


@dataclass(frozen=True, slots=True)
class CheckInReport:
    """One user check-in captured from the CLI."""

    completed: bool
    time_spent: str
    progress: str
    blockers: str
    energy: str
    notes: str


@dataclass(frozen=True, slots=True)
class AdjustedPlan:
    """An adjusted Markdown plan and its file path."""

    title: str
    markdown: str
    output_path: Path


class TrackerError(RuntimeError):
    """Raised when the tracker cannot adjust a plan."""


class DailyTracker:
    """Adjust an existing learning plan from daily check-ins."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        output_dir: Path | None = None,
        temperature: float = 0.3,
    ) -> None:
        self.client = client
        self.model = model
        self.output_dir = output_dir or Path("plans")
        self.temperature = temperature

    def adjust_plan(
        self,
        plan_title: str,
        plan_markdown: str,
        checkin: CheckInReport,
        recent_checkins_context: str,
        learning_habits: str,
        memory_context: str,
    ) -> AdjustedPlan:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": TRACKER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_prompt(
                        plan_title=plan_title,
                        plan_markdown=plan_markdown,
                        checkin=checkin,
                        recent_checkins_context=recent_checkins_context,
                        learning_habits=learning_habits,
                        memory_context=memory_context,
                    ),
                },
            ],
            temperature=self.temperature,
        )
        markdown = response.choices[0].message.content
        if not markdown or not markdown.strip():
            raise TrackerError("DeepSeek 返回了空调整计划。")

        clean_markdown = markdown.strip()
        output_path = self._write_adjusted_plan(plan_title, clean_markdown)
        return AdjustedPlan(
            title=self._extract_title(clean_markdown, plan_title),
            markdown=clean_markdown,
            output_path=output_path,
        )

    def _build_user_prompt(
        self,
        plan_title: str,
        plan_markdown: str,
        checkin: CheckInReport,
        recent_checkins_context: str,
        learning_habits: str,
        memory_context: str,
    ) -> str:
        return (
            "请根据今日打卡调整后续学习计划。\n\n"
            f"当前计划标题：\n{plan_title}\n\n"
            f"当前完整计划：\n{plan_markdown}\n\n"
            "今日打卡：\n"
            f"- 是否完成今日任务：{'是' if checkin.completed else '否'}\n"
            f"- 学习时长：{checkin.time_spent or '未填写'}\n"
            f"- 今日进展：{checkin.progress or '未填写'}\n"
            f"- 阻碍/卡点：{checkin.blockers or '无'}\n"
            f"- 精力状态：{checkin.energy or '未填写'}\n"
            f"- 备注：{checkin.notes or '无'}\n\n"
            f"最近打卡记录：\n{recent_checkins_context or '暂无'}\n\n"
            f"学习习惯状态：\n{learning_habits or '暂无'}\n\n"
            f"长期记忆：\n{memory_context or '暂无'}\n\n"
            "请输出调整后的完整 Markdown 计划。"
        )

    def _write_adjusted_plan(self, plan_title: str, markdown: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "_", plan_title.lower().strip())
        normalized = normalized.strip("_")[:60]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"{normalized or 'learning_plan'}_adjusted_{timestamp}.md"
        output_path.write_text(markdown + "\n", encoding="utf-8")
        return output_path

    def _extract_title(self, markdown: str, fallback: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip()
        return fallback.strip() or "调整后的学习计划"
